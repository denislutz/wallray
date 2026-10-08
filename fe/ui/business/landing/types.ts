export type LandingCopy = {
  banner: string;
  nav: {
    what: string;
    why: string;
    how: string;
    who: string;
    howMuch: string;
  };
  hero: {
    eyebrow: string;
    headline: string;
    subhead: string;
    ctaPrimary: string;
    ctaSecondary: string;
    trustLine: string;
  };
  what: {
    heading: string;
    intro: string;
    bullets: string[];
    closing: string;
  };
  why: {
    heading: string;
    intro: string;
    leadIn: string;
    questions: string[];
    middle: string;
    callout: string;
    renterNote: string;
  };
  how: {
    heading: string;
    steps: { title: string; desc: string }[];
    closing: string;
  };
  who: {
    heading: string;
    quote: string;
  };
  howMuch: {
    heading: string;
    aiTitle: string;
    aiDesc: string;
    aiNote: string;
    aiPrice: string;
    aiDelivery: string;
    note: string;
    ctaBottom: string;
  };
  reel: {
    tagCase: string;
    tagCloseUp: string;
    labelDefect: string;
    labelSeverity: string;
    labelCause: string;
    severityModerate: string;
    severityLow: string;
    replay: string;
    case1Defect: string;
    case1Cause: string;
    case2Defect: string;
    case2Cause: string;
  };
};
