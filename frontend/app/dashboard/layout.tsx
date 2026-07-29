import AuthGuard from "@/components/AuthGuard";
import Nav from "@/components/Nav";
import TopBar from "@/components/TopBar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen bg-slate-50">
        <Nav />
        <div className="ml-60 flex min-h-screen flex-col">
          <TopBar />
          <main className="max-w-6xl px-6 py-8">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
