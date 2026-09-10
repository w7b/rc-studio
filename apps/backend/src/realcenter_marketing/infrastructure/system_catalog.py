"""Local Graphify AST catalog, rebuilt at startup when source hashes change."""
import hashlib
import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from realcenter_marketing.infrastructure.persistence.filesystem import read_json


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class SystemCatalog:
    def __init__(self, root, *, sources=None, workspace=None):
        self.root = root
        self.sources = sources
        self.workspace = workspace or root.parent
        self.directory = root / 'campaigns' / 'system' / 'graphify-out'
        self.state = {'status': 'pending'}
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self.rebuild, daemon=True, name='graphify-catalog')
        self._thread.start()

    def close(self):
        if self._thread:
            self._thread.join()

    def rebuild(self):
        self.state = {'status': 'building'}
        try:
            from graphify.extract import extract
            from graphify.build import build_from_json
            from graphify.cluster import cluster, score_all
            from graphify.export import to_json
            from graphify.diagnostics import diagnose_extraction
            bases = self.sources or [self.root / 'src', self.root / 'agents', self.root / 'config', self.root / 'docs',
                     self.root / 'brand', self.root.parent / 'front-end' / 'src']
            files = sorted({p.resolve() for base in bases if base.is_dir() for p in base.rglob('*')
                if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(base.resolve())
                and not {'static', '__pycache__', 'node_modules'} & set(p.parts)
                and p.suffix in {'.py', '.js', '.jsx', '.ts', '.tsx', '.css', '.json', '.md'}})
            hashes = {(p.relative_to(self.workspace).as_posix() if p.is_relative_to(self.workspace) else 'data/' + p.relative_to(self.root).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
            old = read_json(self.directory / 'manifest.json', {})
            if old.get('hashes') == hashes and (self.directory / 'graph.json').is_file():
                self.state = {'status': 'ready', 'changed': False}
                return
            code = [p for p in files if p.suffix in {'.py', '.js', '.jsx', '.ts', '.tsx'}]
            # Local AST only. Never dispatch semantic extraction or use provider keys.
            extraction = extract(code, cache_root=self.directory, root=self.workspace, parallel=False)
            graph = build_from_json(extraction, root=str(self.workspace), directed=True)
            if not graph.number_of_nodes():
                raise ValueError('Nenhum símbolo extraído')
            communities = cluster(graph)
            cohesion = score_all(graph, communities)
            labels = {}
            for cid, ids in communities.items():
                names = [Path(graph.nodes[n].get('source_file', 'Sistema')).stem for n in ids]
                labels[cid] = ' / '.join(name for name, _ in Counter(names).most_common(2))
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.directory / 'graph.next.json'
            to_json(graph, communities, str(temporary), force=True, community_labels=labels)
            # A complete rescan deliberately permits removing deleted symbols.
            temporary.replace(self.directory / 'graph.json')
            previous = old.get('hashes', {})
            now = datetime.now(timezone.utc).isoformat()
            change = {'time': now, 'added': sorted(hashes.keys() - previous.keys()),
                      'removed': sorted(previous.keys() - hashes.keys()),
                      'modified': sorted(k for k in hashes.keys() & previous.keys() if hashes[k] != previous[k])}
            manifest = {'hashes': hashes, 'updated_at': now, 'files': len(files), 'code_files': len(code),
                        'nodes': graph.number_of_nodes(), 'edges': graph.number_of_edges(),
                        'communities': len(communities), 'input_tokens': 0, 'output_tokens': 0,
                        'cohesion': cohesion, 'health': diagnose_extraction(extraction, directed=True),
                        'history': (old.get('history', []) + [change])[-50:]}
            atomic_json(self.directory / 'manifest.json', manifest)
            report = f'# Catálogo Graphify\n\nAtualizado: {now}\n\n{len(files)} arquivos; {graph.number_of_nodes()} nós; {graph.number_of_edges()} relações.\n\nExtração AST local; 0 tokens de entrada e saída. Documentos são catalogados por caminho e hash; conteúdo semântico não é inferido.\n\n'
            report += '\n'.join(f'- {labels[cid]}: coesão {score}' for cid, score in cohesion.items())
            report += f'\n\nLimitações: {manifest["health"]["dangling_endpoint_edges"]} relações com destino não resolvido; {manifest["health"]["directed_same_endpoint_collapsed_edges"]} relações agrupadas. O mapa é parcial.\n'
            (self.directory / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')
            self.state = {'status': 'ready', 'changed': True}
        except Exception as exc:
            self.state = {'status': 'failed', 'error_type': type(exc).__name__,
                          'message': 'Não foi possível atualizar o mapa. O último catálogo foi preservado.'}

    def snapshot(self):
        manifest = read_json(self.directory / 'manifest.json', {})
        return {**{k: v for k, v in manifest.items() if k != 'hashes'}, **self.state,
                'files_catalog': list(manifest.get('hashes', {})),
                'graph': read_json(self.directory / 'graph.json', {'nodes': [], 'links': []})}


def system_activity(root):
    events = []
    paths = list((root / 'campaigns' / 'runs').glob('run-*/events.jsonl'))
    paths += list((root / 'campaigns' / 'brief-assists').glob('*/events.jsonl'))
    for path in paths:
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append({'run_id': path.parent.name, **{k: event[k] for k in
                ('time', 'event', 'agent', 'input_tokens', 'output_tokens', 'error_type', 'card') if k in event}})
    return sorted(events, key=lambda e: e.get('time', ''), reverse=True)[:250]


def usage_audit(root):
    groups = {}
    records = []
    paths = list((root / 'campaigns' / 'runs').glob('run-*/usage.json'))
    paths += list((root / 'campaigns' / 'brief-assists').glob('*/usage.json'))
    for path in paths:
        usage = read_json(path, {})
        model = usage.get('text', {}).get('model', 'unknown')
        records.append({'id': path.parent.name, 'kind': 'brief-assist' if path.parent.parent.name == 'brief-assists' else 'campaign',
                        'text': usage.get('text', {}), 'image': usage.get('image', {})})
        for name, item in usage.get('text', {}).get('by_agent', {}).items():
            key = (name, model)
            bucket = groups.setdefault(key, {'agent': name, 'model': model, 'requests': 0, 'input_tokens': 0,
                'output_tokens': 0, 'cached_input_tokens': 0, 'cache_write_input_tokens': 0})
            for field in ('requests', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_input_tokens'):
                bucket[field] += int(item.get(field, 0) or 0)
    rows = sorted(groups.values(), key=lambda r: r['input_tokens'], reverse=True)
    events = system_activity(root)
    return {'agents': rows, 'records': records, 'record_count': len(records),
            'input_tokens': sum(r['input_tokens'] for r in rows), 'output_tokens': sum(r['output_tokens'] for r in rows),
            'recent_repairs': sum(e['event'] == 'repair_started' for e in events),
            'notes': ['O Director normalmente faz quatro chamadas: três delegações e a revisão final.',
                      'Especialistas: uma chamada por entrega; correção de schema pode exigir uma tentativa adicional.',
                      'Removida a cópia duplicada das entregas do system prompt do Director; resultados integrais permanecem no histórico.',
                      'Modelos, revisão final e contexto factual dos especialistas foram mantidos.',
                      'Sem comparação live antes/depois, não há percentual de economia ou equivalência editorial comprovado.']}
