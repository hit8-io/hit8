export interface HomeContent {
  hero: {
    badge: string;
    headline: string;
    subHeadline: string;
    description: string;
  };
  features: Array<{
    title: string;
    description: string;
    icon: string;
  }>;
}

export const homeContent: HomeContent = {
  hero: {
    badge: "Redefining Consultancy",
    headline: "The Future of",
    subHeadline: "Transparent Consulting",
    description: "We replace the \"black box\" of traditional consulting with iter8, a transparent platform where you see every step, assumption, and data point in real-time."
  },
  features: [
    {
      title: "Radical Transparency",
      description: "No black boxes. You see all data inputs, steps taken, and assumptions made via our platform.",
      icon: "eye"
    },
    {
      title: "Repeatable Workflows",
      description: "All steps are auditable. You can redo the analysis yourself. We deliver reusable IP, not just one-off reports.",
      icon: "refresh"
    },
    {
      title: "Human in the Loop",
      description: "Technology enables speed, but experienced consultants ensure quality, context, and strategy.",
      icon: "users"
    },
    {
      title: "Outcome Driven",
      description: "Shared value commercial model. Fixed fee for setup, rewards only when agreed business benefits are realized.",
      icon: "target"
    },
    {
      title: "Fact Based",
      description: "Assessments based on actual system data and process mining, not opinions or interviews.",
      icon: "database"
    },
    {
      title: "Tangible Assets",
      description: "All inputs, outputs, and deliverables are digitally encoded. Available for instant review and future re-use.",
      icon: "box"
    }
  ]
};
