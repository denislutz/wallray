function Logo({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label="WallRay"
      className={className}
    >
      <rect x="12" y="10" width="76" height="80" rx="6" fill="var(--logo-wall)" />
      <polygon points="62,69 74,65 79,75 70,83 60,78" fill="var(--logo-mark)" />
      <polyline
        points="37,19 33,29 39,37 32,47 38,58 34,68 37,79"
        fill="none"
        stroke="var(--logo-mark)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points="39,37 51,42"
        fill="none"
        stroke="var(--logo-mark)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line
        x1="4"
        y1="55"
        x2="96"
        y2="55"
        stroke="var(--logo-ray)"
        strokeWidth="10"
        strokeLinecap="round"
        opacity="0.3"
      />
      <line
        x1="4"
        y1="55"
        x2="96"
        y2="55"
        stroke="var(--logo-ray)"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export { Logo };
