export function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Não foi possível ler a imagem'));
    reader.readAsDataURL(file);
  });
}

export function imageFile(value, name) {
  if (!value) return null;
  const bytes = Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
  const png = bytes[0] === 137;
  return new File([bytes], name + (png ? '.png' : '.jpg'), {
    type: png ? 'image/png' : 'image/jpeg',
  });
}
