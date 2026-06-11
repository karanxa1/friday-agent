import clsx from "clsx";
import type { ReactNode, SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & {
  className?: string;
};

/** Transparent vector icon — stroke-only, no background, inherits `currentColor`. */
export function Icon({
  className,
  children,
  viewBox = "0 0 24 24",
  ...props
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={clsx("block shrink-0", className)}
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

export function createIcon(
  name: string,
  children: ReactNode,
  opts?: { spin?: boolean }
) {
  const Cmp = ({ className, ...props }: IconProps) => (
    <Icon className={clsx(opts?.spin && "animate-spin", className)} {...props}>
      {children}
    </Icon>
  );
  Cmp.displayName = name;
  return Cmp;
}
