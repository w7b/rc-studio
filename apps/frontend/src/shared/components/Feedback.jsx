import React from 'react';

export default function Feedback({ children, action, tone = 'error' }) {
  return (
    <div
      className={`feedback-message ${tone === 'error' ? 'auth-error' : tone === 'warning' ? 'feedback-warning' : 'account-done'}`}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      <span>{children}</span>
      {action}
    </div>
  );
}
