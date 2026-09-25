"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Market openings" },
  { href: "/evidence", label: "Live evidence" },
  { href: "/next-up", label: "Next week" },
  { href: "/gap", label: "Unspoken demand" },
  { href: "/ecosystem", label: "Discovery health" },
  { href: "/map", label: "Adjacent scenes" },
  { href: "/briefs", label: "Creator moves" },
  { href: "/methods", label: "Evidence & methods" },
] as const;

export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary navigation"
      className="flex items-center gap-x-7 overflow-x-auto border-b border-rule"
    >
      {navItems.map(({ href, label }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`focus-ring -mb-px shrink-0 border-b-2 py-3.5 text-[14px] transition-colors duration-150 ease-out ${
              active
                ? "border-accent font-medium text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
