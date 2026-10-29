/** @type {import('dependency-cruiser').IConfiguration} */
const configuration = {
  forbidden: [
    {name: "no-cycles", severity: "error", from: {}, to: {circular: true}},
    {name: "no-unresolved", severity: "error", from: {}, to: {couldNotResolve: true}},
    {
      name: "inner-layers-stay-pure", severity: "error",
      from: {path: "^frontend/src/(domain|application)/"},
      to: {path: "^frontend/src/(adapters|infrastructure|presentation|composition)/"},
    },
    {
      name: "inner-layers-no-frameworks", severity: "error",
      from: {path: "^frontend/src/(domain|application)/"},
      to: {path: "(^|/)(node_modules/)?(lit|@lit/[^/]+|vite|home-assistant-js-websocket)(/|$)"},
    },
    {
      name: "presentation-no-concrete-adapters", severity: "error",
      from: {path: "^frontend/src/presentation/"},
      to: {path: "^frontend/src/(adapters|infrastructure|composition)/"},
    },
  ],
  options: {doNotFollow: {path: "node_modules"}, tsPreCompilationDeps: true},
};

export default configuration;
