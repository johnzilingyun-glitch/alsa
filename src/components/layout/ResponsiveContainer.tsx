import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ResponsiveContainerProps {
  children: React.ReactNode;
  className?: string;
  as?: React.ElementType;
}

export function ResponsiveContainer({ children, className, as: Tag = 'div' }: ResponsiveContainerProps) {
  return (
    <Tag className={cn('px-4 py-8 sm:px-6 md:px-12 md:py-12', className)}>
      {children}
    </Tag>
  );
}
