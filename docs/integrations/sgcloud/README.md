# SGCloud futuro

Contrato e mock: src/realcenter_marketing/sgcloud.py.
Métodos internos: get_product, get_stock, get_sales. Não representam endpoints da SGCloud.
Sem campos de preço, valores monetários, escritas, cliente HTTP ou credenciais SGCloud.
Nenhum agente recebe esse adapter no MVP. Mock inicia vazio e recebe fixtures explícitas.
Consulta ausente retorna None, nunca estoque zero presumido. Vendas usam período exato da fixture.
Integrar somente após receber documentação real de autenticação, endpoints e semântica dos dados.

