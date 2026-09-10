# Frontend

React com Vite. `src/app` compõe a interface, `src/features` organiza funcionalidades e `src/shared` contém o cliente HTTP e componentes compartilhados.

Nesta pasta:

```powershell
npm ci
npm run dev
npm run build
```

O build sai em `dist/`. A API deve estar em `127.0.0.1:8765`; o proxy de desenvolvimento preserva `/api`, `/media` e a origem exigida pelo backend. Produção usa a mesma origem para interface e API.
