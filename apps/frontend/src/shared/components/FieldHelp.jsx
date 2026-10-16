import React from 'react';
import { HelpCircle } from '../icons.js';
import Tooltip from './Tooltip.jsx';

// The shared pill tooltip works on pointer hover and keyboard focus.
export default function FieldHelp({ text }) {
  if (!text) return null;
  return (
    <Tooltip text={text} interactive triggerLabel="Mais informações" triggerClassName="field-help">
      <HelpCircle size={16} aria-hidden="true" />
    </Tooltip>
  );
}
