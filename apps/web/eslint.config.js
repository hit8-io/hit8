import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import security from 'eslint-plugin-security';
import sonarjs from 'eslint-plugin-sonarjs';
import noUnsanitized from 'eslint-plugin-no-unsanitized';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: ['dist', 'node_modules', 'coverage', 'eslint.config.js'],
  },
  // 1. Base JS & TS Rules (Upgraded to Type-Checked)
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  // Optional: strict type-checking if you want maximum safety
  // ...tseslint.configs.strictTypeChecked,
  
  // 2. Security Configs (The "Heavy Hitters")
  security.configs.recommended,
  sonarjs.configs.recommended,
  noUnsanitized.configs.recommended,

  // 3. React Configs
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'], // Necessary for React 17+ new JSX transform

  {
    languageOptions: {
      ecmaVersion: 2024,
      globals: globals.browser,
      parserOptions: {
        projectService: true, // Enables type-aware linting automatically
        tsconfigRootDir: import.meta.dirname,
      },
    },
    settings: {
      react: {
        version: 'detect', // Auto-detect React version
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // 4. Custom Rule Overrides
      ...reactHooks.configs.recommended.rules,
      
      // Enforce Vite's HMR best practices
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // Common overrides for convenience
      '@typescript-eslint/no-unused-vars': ['warn', { 
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_' 
      }],
      
      // Floating promises are often bugs in async code (e.g. cloud functions)
      '@typescript-eslint/no-floating-promises': 'error',
      
      // React security specific
      'react/no-danger': 'warn', // Warns if you use dangerouslySetInnerHTML
    },
  }
);
