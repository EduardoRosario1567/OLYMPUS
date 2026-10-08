import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xs",
        "shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset] p-6",
        className
      )}
      {...props}
    />
  );
}

export function CardLabel({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-xs font-medium uppercase tracking-wider text-zinc-500", className)}
      {...props}
    />
  );
}

export function CardValue({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("mt-2 text-3xl font-semibold tracking-tight text-zinc-50", className)}
      {...props}
    />
  );
}
