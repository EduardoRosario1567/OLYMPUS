import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
}

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-xl px-4 py-2.5 text-sm font-medium",
        "transition-colors duration-150 disabled:opacity-50 disabled:pointer-events-none",
        variant === "primary" &&
          "bg-zinc-50 text-zinc-950 hover:bg-zinc-200",
        variant === "secondary" &&
          "border border-white/10 bg-white/[0.04] text-zinc-200 hover:bg-white/[0.08]",
        variant === "ghost" &&
          "bg-transparent text-zinc-300 hover:bg-white/5 border border-white/10",
        className
      )}
      {...props}
    />
  );
}
