import React from 'react';

export default function MetricCard({ label, value, detail, icon: Icon }) {
  return (
    <article className="metric-card">
      <h3 className="title-with-icon">
        {Icon && <Icon size={16} aria-hidden="true" />}
        {label}
      </h3>
      <strong>{value}</strong>
      {detail && <p>{detail}</p>}
    </article>
  );
}
