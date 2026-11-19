import type { ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export default function AuthCard({ title, subtitle, children, footer }: Props) {
  return (
    <main className="card">
      <h1>{title}</h1>
      {subtitle && <p className="muted">{subtitle}</p>}
      <div className="auth-body">{children}</div>
      {footer && <p className="auth-footer">{footer}</p>}
    </main>
  );
}
