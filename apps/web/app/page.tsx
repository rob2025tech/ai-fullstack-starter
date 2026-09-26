import AgentWorkspace from "@/components/agent-workspace";
import Chat from "@/components/chat";
import RetentionQuiz from "@/components/retention-quiz";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center px-4 py-8 sm:py-12">
      <header className="mb-8 w-full max-w-5xl">
        <p className="text-sm font-medium uppercase tracking-[0.16em] text-indigo-600">
          AI + Education Hackathon @ Stanford
        </p>

        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Learn what you don't know.
        </h1>

        <p className="mt-2 max-w-2xl text-black/60">
          Test what you actually retained, identify weak concepts,
          and use spaced repetition to decide what needs review next.
        </p>
      </header>

      <RetentionQuiz />

      <section className="mt-12 w-full max-w-5xl border-t border-black/10 pt-8">
        <details>
          <summary className="cursor-pointer text-sm font-medium text-black/60">
            Agent workspace
          </summary>

          <div className="mt-5 flex justify-center">
            <AgentWorkspace />
          </div>
        </details>
      </section>

      <section className="mt-8 w-full max-w-5xl border-t border-black/10 pt-8">
        <details>
          <summary className="cursor-pointer text-sm font-medium text-black/60">
            Existing AI chat
          </summary>

          <div className="mt-5">
            <Chat />
          </div>
        </details>
      </section>
    </main>
  );
}