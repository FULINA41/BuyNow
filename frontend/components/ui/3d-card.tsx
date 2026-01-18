"use client";

import { cn } from "@/lib/utils";
import React, { createContext, useContext, useRef, useState } from "react";

const CardContext = createContext<{
  width?: number;
  height?: number;
}>({
  width: 0,
  height: 0,
});

export const CardContainer = ({
  children,
  className,
  containerClassName,
}: {
  children?: React.ReactNode;
  className?: string;
  containerClassName?: string;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  React.useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { offsetWidth, offsetHeight } = containerRef.current;
        setDimensions({ width: offsetWidth, height: offsetHeight });
      }
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  return (
    <CardContext.Provider value={dimensions}>
      <div
        ref={containerRef}
        className={cn("relative", containerClassName)}
      >
        <div className={cn("relative", className)}>{children}</div>
      </div>
    </CardContext.Provider>
  );
};

export const CardBody = ({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) => {
  return (
    <div
      className={cn(
        "h-96 w-96 [transform-style:preserve-3d]  [&>*]:[transform-style:preserve-3d]",
        className
      )}
    >
      {children}
    </div>
  );
};

export const CardItem = ({
  as: Tag = "div",
  children,
  className,
  translateX = 0,
  translateY = 0,
  translateZ = 0,
  rotateX = 0,
  rotateY = 0,
  rotateZ = 0,
  ...rest
}: {
  as?: React.ElementType;
  children: React.ReactNode;
  className?: string;
  translateX?: number | string;
  translateY?: number | string;
  translateZ?: number | string;
  rotateX?: number | string;
  rotateY?: number | string;
  rotateZ?: number | string;
}) => {
  const { width, height } = useContext(CardContext);
  const x = typeof translateX === "number" ? translateX : 0;
  const y = typeof translateY === "number" ? translateY : 0;
  const z = typeof translateZ === "number" ? translateZ : 0;
  const rx = typeof rotateX === "number" ? rotateX : 0;
  const ry = typeof rotateY === "number" ? rotateY : 0;
  const rz = typeof rotateZ === "number" ? rotateZ : 0;

  return (
    <Tag
      className={cn("w-fit transition-transform duration-200 ease-out", className)}
      style={{
        transformStyle: "preserve-3d",
        transform: `translateX(${x}px) translateY(${y}px) translateZ(${z}px) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg)`,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
};
