export const links = {
  notion: "https://www.notion.so/",
  email: "hello@happitatlabs.com",
  github: "https://github.com/happitatlabs",
};

export type Product = {
  name: string;
  summary: string;
  detail: string;
  signal: string;
  status: "Private Beta" | "MVP Complete" | "Coming Soon";
  path: string;
};

export const capabilityTags = ["문제 구조화", "AI 활용", "MVP", "UI/UX", "업무 자동화"];

export const processSteps = [
  {
    title: "Discover",
    subtitle: "문제 발견",
    description:
      "사용자가 어디에서 막히는지, 무엇을 이해하기 어려워하는지 먼저 관찰합니다.",
  },
  {
    title: "Structure",
    subtitle: "정보 구조화",
    description:
      "흩어진 정보와 복잡한 흐름을 사람이 이해할 수 있는 구조로 정리합니다.",
  },
  {
    title: "Build",
    subtitle: "MVP 제작",
    description:
      "AI와 소프트웨어를 활용해 작고 검증 가능한 제품으로 만듭니다.",
  },
  {
    title: "Validate",
    subtitle: "사용 흐름 검증",
    description:
      "실제 사용 흐름에서 불편한 지점을 확인하고 다음 개선 방향을 찾습니다.",
  },
];

export const products = [
  {
    name: "Happy Habitat",
    summary:
      "바쁜 일상 속에서 잊기 쉬운 회복의 순간을 기록하고, 하루를 다시 이어 갈 힘을 남기는 행복 기록 앱",
    detail:
      "Happy Habitat은 바쁜 일상 속에서 놓치기 쉬운 회복의 순간을 기록하고, 하루를 다시 이어 갈 힘을 남기는 행복 기록 앱입니다.",
    signal: "RECORD",
    status: "Private Beta",
    path: "/products/happy-habitat",
  },
  {
    name: "SQL Diagnoser",
    summary:
      "복잡한 SQL을 사람이 이해할 수 있는 구조로 해석하고, 다음 행동을 제안하는 진단 도구",
    detail:
      "SQL Diagnoser는 복잡한 SQL을 사람이 이해할 수 있는 구조로 해석하고, 다음 행동을 제안하는 진단 도구입니다.",
    signal: "ANALYZE",
    status: "MVP Complete",
    path: "/products/sql-diagnoser",
  },
  {
    name: "Dot Code Editor",
    summary:
      "픽셀 작업을 코드와 연결해 작은 창작물을 빠르게 만들 수 있도록 돕는 도트 작업 도구",
    detail:
      "Dot Code Editor는 픽셀 작업을 코드와 연결해 작은 창작물을 빠르게 만들 수 있도록 돕는 도트 작업 도구입니다.",
    signal: "CREATE",
    status: "MVP Complete",
    path: "/products/dot-code-editor",
  },
] satisfies Product[];
