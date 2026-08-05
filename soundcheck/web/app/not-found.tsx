import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <EmptyState
      title="That scene is outside the decision set"
      message="The route or canonical genre is not part of Soundcheck’s current evidence taxonomy."
      href="/"
      linkLabel="Review market openings"
    />
  );
}
