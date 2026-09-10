import React, { useEffect, useState } from 'react';
import { UploadCloud, X, Image } from 'lucide-react';

export default function UploadField({ label, file, onChange, optional = false }) {
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!file) {
      setPreview('');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function choose(candidate) {
    if (!candidate) return;
    if (!['image/png', 'image/jpeg'].includes(candidate.type) || candidate.size > 8 * 1024 * 1024) {
      setError('Escolha PNG ou JPEG de até 8 MB.');
      return;
    }
    setError('');
    onChange(candidate);
  }
  return (
    <div>
      <span className="field-label">
        {label}
        {optional && <small>opcional</small>}
      </span>
      <div
        className={'upload ' + (file ? 'has-file' : '')}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          choose(e.dataTransfer.files[0]);
        }}
      >
        {preview ? <img src={preview} alt={label} /> : <UploadCloud size={24} />}
        <label className="cursor-pointer">
          <strong>{file ? file.name : 'Clique ou arraste uma imagem'}</strong>
          <span>PNG ou JPEG · até 8 MB</span>
          <input
            aria-label={label}
            type="file"
            accept="image/png,image/jpeg"
            className="sr-only"
            onChange={(e) => {
              choose(e.target.files[0]);
              e.target.value = '';
            }}
          />
        </label>
        {file && (
          <button
            type="button"
            className="icon-button"
            aria-label={'Remover ' + label}
            onClick={() => onChange(null)}
          >
            <X size={16} />
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-red-700 text-sm mt-2">
          {error}
        </p>
      )}
    </div>
  );
}
