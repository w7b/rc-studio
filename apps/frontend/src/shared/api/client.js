export async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Não foi possível conectar ao app');
  return data;
}
export const post = (path, data, token) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-App-Token': token },
    body: JSON.stringify(data),
  });
export function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Não foi possível ler a imagem'));
    reader.readAsDataURL(file);
  });
}
