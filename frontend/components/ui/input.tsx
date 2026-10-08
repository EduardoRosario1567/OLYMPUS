import { cn } from "@/lib/utils";
import type { InputHTMLAttributes } from "react";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5 text-sm text-zinc-100",
        "placeholder:text-zinc-600 outline-hidden transition-colors duration-150",
        "focus:border-zinc-400/40 focus:bg-white/[0.04]",
        className
      )}
      {...props}
    />
  );
}
