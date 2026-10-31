import type { Metadata } from "next";
import { DatasetBrowser } from "@/components/DatasetBrowser";
import { PageHead } from "@/components/PageHead";
import { REVIEW, STORE } from "@/lib/content";

export const metadata: Metadata = {
  title: "Dataset",
  description: "The open half of dataset v1: shopping requests with a human label and the trap an agent can fall into.",
  alternates: { canonical: "/dataset" },
};

export default function DatasetPage() {
  return (
    <main>
      <PageHead kicker="Dataset v1" title="What people ask, and what would be right to buy">
        <p className="text-muted">
          {STORE.tasks} tasks from {STORE.templates} trap templates over the sandbox catalog. Each has a request in a
          person&apos;s words, a label saying which purchase is right (or that buying nothing is), and at least one
          trap the payment mandate would let through. Here is the open half; ten of its tasks are in Russian. The other{" "}
          {STORE.hidden} are kept out of the repository, but the generator&apos;s seed is in it, so anyone can rebuild
          them: treat all {STORE.tasks} as public. Dataset v2, {STORE.v2Open} open tasks from {STORE.v2Templates}{" "}
          templates where strong models made mistakes, is in <code>data/tasks_v2.jsonl</code> in the repository.
        </p>
      </PageHead>

      <section className="column">
        <div className="doc">
          <h2 id="labels"><a href="#labels">How to read a task</a></h2>
          <p>
            <strong>right</strong> is the label: the conditions a right purchase meets, as data the scorer checks
            (family, colour, size, returnable, delivery days, a price ceiling, a total). <strong>trap</strong> is the
            tempting wrong purchase the generator made sure exists. Agents are scored against the label, never against
            the guard.
          </p>

          <h2 id="review"><a href="#review">How it was reviewed</a></h2>
          <p>
            The generator only proposes. One person reviewed it: {REVIEW.rowByRow} tasks row by row, and every other
            template through a concrete question about which purchase is right. The other tasks were not read one by
            one, and with a single reviewer there is no inter-annotator agreement to report. The review changed two
            templates:
          </p>
          <ul>
            {REVIEW.fixed.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <p>
            English tasks were reviewed through a Russian translation, with labels translated by code, not by a model.
            Whether the English sounds natural was checked by a model, not a person.
          </p>
        </div>

        <h2 id="tasks" className="mt-20 text-[28px] font-semibold tracking-tight">
          The open tasks
        </h2>
        <div className="mt-6">
          <DatasetBrowser />
        </div>
      </section>
    </main>
  );
}
