import { useCurrentUser } from "~/hooks/useCurrentUser";

export function Header() {
  const { data: user } = useCurrentUser();

  return (
    <header className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
      <span className="text-lg font-semibold">__PROJECT_NAME__</span>
      <span className="text-sm text-gray-500">{user ? user.email : "Not signed in"}</span>
    </header>
  );
}
