import type { Route } from "./+types/home";
import { Header } from "~/components/Header";
import { useCurrentUser } from "~/hooks/useCurrentUser";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "__PROJECT_NAME__" },
    { name: "description", content: "Base Go + React starting point" },
  ];
}

export default function Home() {
  const { data: user, isPending, error } = useCurrentUser();

  return (
    <>
      <Header />
      <main className="mx-auto max-w-2xl px-6 py-12">
        <h1 className="text-2xl font-bold">__PROJECT_NAME__</h1>
        <p className="mt-2 text-gray-500">
          A base Go + React starter with database, auth, and health-check wiring.
        </p>
        {isPending && <p className="mt-6 text-sm text-gray-500">Loading session…</p>}
        {error && (
          <p className="mt-6 text-sm text-gray-500">Not signed in. Head to /login.</p>
        )}
        {user && <p className="mt-6 text-sm">Signed in as {user.email}</p>}
      </main>
    </>
  );
}
