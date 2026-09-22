import React from 'react';
import { HelpCircle } from 'lucide-react';
import Tooltip from './Tooltip.jsx';

// The shared pill tooltip works on pointer hover and keyboard focus.
export default function FieldHelp({ text }) {
  if (!text) return null;
  return (
    <Tooltip text={text}>
      <span className="field-help" aria-label="Mais informações" role="img" tabIndex={0}>
        <HelpCircle size={13} aria-hidden="true" />
      </span>
    </Tooltip>
  );
}
