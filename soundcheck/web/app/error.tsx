"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/ui";

export default function ErrorPage({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorState
      title="This decision could not be prepared"
      message="The evidence is safe. Refresh the page or try again after the data service updates."
    />
  );
}
