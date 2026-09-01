import Chat from "@/components/chat";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center px-4 py-8">
      <header className="mb-6 text-center">
        <h1 className="text-2xl font-semibold">AI Fullstack Starter</h1>
        <p className="text-sm opacity-70">
          Next.js web client &rarr; /api/v1 contract &rarr; FastAPI backend
        </p>
      </header>
      <Chat />
    </main>
  );
}
