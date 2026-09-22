import React, { useLayoutEffect, useRef } from 'react';

export default function Textarea({ value, style, onInput, ...props }) {
  const ref = useRef(null);
  const grow = () => {
    if (!ref.current) return;
    ref.current.style.height = 'auto';
    ref.current.style.height = `${Math.min(420, ref.current.scrollHeight + 2)}px`;
  };
  useLayoutEffect(grow, [value]);
  return (
    <textarea
      className="resize-none"
      {...props}
      ref={ref}
      value={value}
      style={{ ...style, resize: 'none' }}
      onInput={(event) => {
        grow();
        onInput?.(event);
      }}
    />
  );
}
