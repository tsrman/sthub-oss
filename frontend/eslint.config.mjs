import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

export default [
  // public/ holds the vendored Monaco bundle — upstream minified code, not ours.
  { ignores: ['.next/**', 'coverage/**', 'public/**', 'next-env.d.ts'] },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    rules: {
      'react-hooks/exhaustive-deps': 'warn',
      // The React Compiler rules flag pre-existing load-on-mount effects and a
      // Date.now() slug. They are real but need a behavioural refactor, so they
      // stay visible as warnings instead of blocking the build.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
];
