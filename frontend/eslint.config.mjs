// ESLint flat config（F-08）。
//
// 之前 package.json 有 `lint` 脚本但项目根目录无配置文件、依赖也未安装，
// `npm run lint` 会失败。本文件启用 Next.js 官方推荐规则集 + TypeScript + React Hooks。
//
// 使用前请先安装依赖：npm install
//（eslint / eslint-config-next / eslint-plugin-react-hooks 已写入 devDependencies）
//
// 适配 eslint-config-next v16（Next.js 16 配套）的 flat config 导出：
//   flatConfigs.recommended / flatConfigs.coreWebVitals / flatConfigs.react

import next from "eslint-config-next"

const nextConfigs = next.flatConfigs
  ? [nextConfigs.recommended, nextConfigs.coreWebVitals, nextConfigs.react].filter(Boolean)
  : []

export default [
  ...nextConfigs,

  // 项目级规则覆盖
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "build/**",
      "coverage/**",
    ],
    rules: {
      // 与项目现状保持一致：不强制要求每个函数显式返回类型（部分 lambda/箭头未标注）
      "@typescript-eslint/explicit-function-return-type": "off",
      // next.config.mjs / eslint.config.mjs 等 .mjs 配置文件允许 require
      "@typescript-eslint/no-require-imports": "off",
    },
  },
]
