import { promises as fs } from "node:fs";
import path from "node:path";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PageHeader, Panel } from "@/components/ui";

async function readMethodFile(filename: string): Promise<string> {
  return fs.readFile(
    path.join(process.cwd(), "..", "docs", filename),
    "utf8",
  );
}

export default async function MethodsPage() {
  const [measurementMethod, forecastMethod, taxonomyMethod, coverageMethod] =
    await Promise.all([
    readMethodFile("metrics_v2.md"),
    readMethodFile("forecasting_v2.md"),
    readMethodFile("taxonomy.md"),
    readMethodFile("data_coverage.md"),
  ]);
  return (
    <>
      <PageHeader
        eyebrow="Trust layer · Taxonomy 2.0.0"
        title="See exactly what earned a recommendation."
        description="Soundcheck publishes its genre definitions, coverage gates, formulas, priors, held-out tests, and limitations. Use this record to decide how much confidence—and commitment—a recommendation deserves."
        action={
          <nav className="flex items-center gap-2 text-[10px]">
            <a
              href="#taxonomy"
              className="focus-ring rounded-sm border hairline px-3 py-2 text-muted hover:border-ink/40 hover:text-ink"
            >
              Taxonomy
            </a>
            <a
              href="#coverage"
              className="focus-ring rounded-sm border hairline px-3 py-2 text-muted hover:border-ink/40 hover:text-ink"
            >
              Coverage gates
            </a>
            <a
              href="#metrics"
              className="focus-ring rounded-sm border hairline px-3 py-2 text-muted hover:border-ink/40 hover:text-ink"
            >
              How openings are measured
            </a>
            <a
              href="#forecasting"
              className="focus-ring rounded-sm border hairline px-3 py-2 text-muted hover:border-ink/40 hover:text-ink"
            >
              How calls are validated
            </a>
          </nav>
        }
      />
      <div className="space-y-8">
        <MethodDocument id="taxonomy" source={taxonomyMethod} />
        <MethodDocument id="coverage" source={coverageMethod} />
        <MethodDocument id="metrics" source={measurementMethod} />
        <MethodDocument id="forecasting" source={forecastMethod} />
      </div>
    </>
  );
}

function MethodDocument({
  id,
  source,
}: {
  id: string;
  source: string;
}) {
  return (
    <Panel className="scroll-mt-24">
      <article id={id} className="method-copy px-6 py-9 sm:px-10 sm:py-12">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
      </article>
    </Panel>
  );
}
