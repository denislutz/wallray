"use client";

import AccountS from "@/services/business/AccountS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingS from "@/services/tech/RoutingS";
import { cn } from "@/services/tech/TailwindS";
import { ClipboardCheck, ClipboardList, User } from "lucide-react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ============================================================================
// Public
// ============================================================================

export function BottomNav() {
  const { status } = useSession();
  const { token } = AuthS.useAuth();
  const { me } = AccountS.useMe(token);
  const pathname = usePathname();
  const t = UISessionS.useT();

  if (status !== "authenticated") return null;

  const isExpert = me?.role === "expert_review" || me?.role === "admin";

  const tabs = [
    {
      key: "reports",
      href: RoutingS.paths.reports(),
      Icon: ClipboardList,
      label: t("nav_reports"),
    },
    ...(isExpert
      ? [
          {
            key: "reviews",
            href: RoutingS.paths.expertReviews(),
            Icon: ClipboardCheck,
            label: t("nav_reviews"),
          },
        ]
      : []),
    { key: "account", href: RoutingS.paths.account(), Icon: User, label: t("nav_account") },
  ] as const;

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex border-t bg-background">
      {tabs.map(({ key, href, Icon, label }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={key}
            href={href}
            className={cn(
              "flex flex-1 flex-col items-center gap-1 py-3 text-xs transition-colors",
              active ? "text-foreground" : "text-muted-foreground"
            )}
          >
            <Icon className="size-5" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
