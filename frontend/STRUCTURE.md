# S2PNexus Frontend - Next.js with TypeScript and TailwindCSS
# This is the structure only for Phase 1

# package.json
{
  "name": "s2pnexus-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "axios": "^1.7.0",
    "zustand": "^4.5.0",
    "react-hook-form": "^7.51.0",
    "@hookform/resolvers": "^3.3.0",
    "zod": "^3.23.0",
    "date-fns": "^3.6.0",
    "lucide-react": "^0.378.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.3.0"
  },
  "devDependencies": {
    "@types/node": "^20.12.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.4.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19",
    "eslint": "^8.57.0",
    "eslint-config-next": "14.2.0",
    "@typescript-eslint/eslint-plugin": "^7.0.0",
    "@typescript-eslint/parser": "^7.0.0"
  }
}

# tsconfig.json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}

# next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    domains: ['localhost'],
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;

# tailwind.config.ts
import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
      },
    },
  },
  plugins: [],
};

export default config;

# postcss.config.js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

# .eslintrc.json
{
  "extends": ["next/core-web-vitals"],
  "rules": {
    "@typescript-eslint/no-unused-vars": "warn",
    "react/no-unescaped-entities": "off"
  }
}

# Directory structure:
# frontend/
# ├── src/
# │   ├── app/
# │   │   ├── layout.tsx
# │   │   ├── page.tsx
# │   │   ├── globals.css
# │   │   ├── login/
# │   │   │   └── page.tsx
# │   │   ├── register/
# │   │   │   └── page.tsx
# │   │   ├── dashboard/
# │   │   │   └── page.tsx
# │   │   ├── suppliers/
# │   │   │   └── page.tsx
# │   │   ├── contracts/
# │   │   │   └── page.tsx
# │   │   ├── documents/
# │   │   │   └── page.tsx
# │   │   ├── analytics/
# │   │   │   └── page.tsx
# │   │   └── ai/
# │   │       └── page.tsx
# │   ├── components/
# │   │   ├── ui/
# │   │   │   ├── Button.tsx
# │   │   │   ├── Input.tsx
# │   │   │   ├── Card.tsx
# │   │   │   ├── Table.tsx
# │   │   │   ├── Modal.tsx
# │   │   │   └── Dropdown.tsx
# │   │   ├── layout/
# │   │   │   ├── Header.tsx
# │   │   │   ├── Sidebar.tsx
# │   │   │   └── Footer.tsx
# │   │   └── forms/
# │   │       ├── LoginForm.tsx
# │   │       ├── RegisterForm.tsx
# │   │       ├── SupplierForm.tsx
# │   │       └── ContractForm.tsx
# │   ├── lib/
# │   │   ├── api.ts
# │   │   ├── auth.ts
# │   │   ├── utils.ts
# │   │   └── validations.ts
# │   ├── hooks/
# │   │   ├── useAuth.ts
# │   │   ├── useApi.ts
# │   │   └── useDebounce.ts
# │   ├── store/
# │   │   ├── authStore.ts
# │   │   └── uiStore.ts
# │   └── types/
# │       ├── api.ts
# │       ├── user.ts
# │       ├── supplier.ts
# │       ├── contract.ts
# │       └── document.ts
# ├── public/
# ├── package.json
# ├── tsconfig.json
# ├── next.config.js
# ├── tailwind.config.ts
# ├── postcss.config.js
# ├── .eslintrc.json
# └── Dockerfile