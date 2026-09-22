import React, { useId, useState } from 'react';

// Keep native field semantics, but own validation messages and focus consistently.
export default function Form({ children, onSubmit, ...props }) {
  const [error, setError] = useState('');
  const errorId = useId();
  function submit(event) {
    const fields = [...event.currentTarget.elements].filter((field) => field.willValidate);
    const invalid = fields.find((field) => !field.validity.valid);
    fields.forEach((field) => {
      field.setAttribute('aria-invalid', String(!field.validity.valid));
      const descriptions = (field.getAttribute('aria-describedby') || '')
        .split(' ')
        .filter((id) => id && id !== errorId);
      if (!field.validity.valid) descriptions.push(errorId);
      if (descriptions.length) field.setAttribute('aria-describedby', descriptions.join(' '));
      else field.removeAttribute('aria-describedby');
    });
    if (invalid) {
      event.preventDefault();
      const label = (
        invalid.labels?.[0]?.textContent ||
        invalid.getAttribute('aria-label') ||
        'Campo'
      )
        .trim()
        .slice(0, 70);
      setError(
        `${label}: ${invalid.validity.valueMissing ? 'preencha este campo.' : invalid.validity.typeMismatch ? 'confira o formato informado.' : 'confira o valor e os limites permitidos.'}`
      );
      invalid.focus();
      return;
    }
    setError('');
    onSubmit?.(event);
  }
  return (
    <form {...props} noValidate onSubmit={submit}>
      {error && (
        <p id={errorId} className="auth-error" role="alert">
          {error}
        </p>
      )}
      {children}
    </form>
  );
}
