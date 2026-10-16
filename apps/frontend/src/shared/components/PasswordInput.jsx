import React, { useState } from 'react';
import { Lock, LockOpen } from '../icons.js';

export default function PasswordInput({ visibilityLabel = 'senha', ...props }) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="password-control">
      <input {...props} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        aria-label={`${visible ? 'Ocultar' : 'Mostrar'} ${visibilityLabel}`}
        aria-controls={props.id}
        aria-pressed={visible}
        disabled={props.disabled}
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? (
          <LockOpen size={18} aria-hidden="true" />
        ) : (
          <Lock size={18} aria-hidden="true" />
        )}
      </button>
    </span>
  );
}
