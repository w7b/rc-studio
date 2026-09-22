import React from 'react';

// Marks a field the form will not submit without. Colour alone would not carry the
// meaning for a colour-blind reader, so the asterisk has a text label behind it.
export default function Required() {
  return (
    <abbr className="required-mark" title="Campo obrigatório" aria-label="obrigatório">
      *
    </abbr>
  );
}
