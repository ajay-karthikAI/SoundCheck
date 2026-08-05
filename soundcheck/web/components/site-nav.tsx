"use client";

import {
  Activity,
  AudioLines,
  FileText,
  Gauge,
  Map,
  Radar,
  Radio,
  Telescope,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Market openings", icon: Radar },
  { href: "/evidence", label: "Live evidence", icon: Radio },
  { href: "/next-up", label: "Next week", icon: Telescope },
  { href: "/gap", label: "Unspoken demand", icon: AudioLines },
  { href: "/ecosystem", label: "Discovery health", icon: Activity },
  { href: "/map", label: "Adjacent scenes", icon: Map },
  { href: "/briefs", label: "Creator moves", icon: FileText },
  { href: "/methods", label: "Evidence & methods", icon: Gauge },
] as const;

export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary navigation"
      className="flex items-center gap-1 overflow-x-auto pb-px"
    >
      {navItems.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`focus-ring flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-[13px] transition-colors duration-150 ease-out ${
              active
                ? "bg-white/[0.07] text-white"
                : "text-white/45 hover:bg-white/[0.035] hover:text-white/80"
            }`}
          >
            <Icon
              aria-hidden="true"
              className={active ? "text-accent" : ""}
              size={14}
              strokeWidth={1.7}
            />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
