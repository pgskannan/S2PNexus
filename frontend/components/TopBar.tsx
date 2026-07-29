// Slim branded header above the page content -- fills the empty space that
// used to sit above each page's own heading, and gives every dashboard page
// a consistent wordmark + tagline instead of jumping straight into content.
export default function TopBar() {
  return (
    <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-4">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.svg" alt="" className="h-8 w-8" />
      <div>
        <p className="text-xl font-bold tracking-tight text-brand-700">
          S2P Nexus
        </p>
        <p className="text-xs font-medium text-slate-500">
          Enterprise procurement power, built for small business.
        </p>
      </div>
    </header>
  );
}
