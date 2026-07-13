# ContentGenie Web Studio

The desktop-first ContentGenie interface is built with Next.js, React, TypeScript, Tailwind CSS, Motion, shadcn/ui, Radix UI, and Lucide. Its Moonlit Paper design system uses an animated glass application shell and a custom code-native SVG identity.

```bash
npm install
npm run dev
```

Run the production build and desktop interaction suite with:

```bash
npm run build
npm run test:e2e
```

Development runs on port 3000 and expects the private ContentGenie FastAPI service on `127.0.0.1:31417`. For the complete production launcher, run `python runContentGenie.py` from the repository root.
