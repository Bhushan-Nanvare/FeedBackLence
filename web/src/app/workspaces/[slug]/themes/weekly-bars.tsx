import type { ThemeWeek } from "@/lib/api";

const BAR_WIDTH = 10;
const BAR_GAP = 3;
const HEIGHT = 32;

/** A small bar chart of reports per week, drawn inline so no chart library is needed. */
export function WeeklyBars({ weeks, title }: { weeks: ThemeWeek[]; title?: string }) {
  if (weeks.length === 0) {
    return null;
  }
  const highest = Math.max(...weeks.map((week) => week.item_count), 1);
  const width = weeks.length * (BAR_WIDTH + BAR_GAP) - BAR_GAP;

  return (
    <svg
      width={width}
      height={HEIGHT}
      viewBox={`0 0 ${width} ${HEIGHT}`}
      role="img"
      aria-label={
        title ??
        `Reports per week: ${weeks.map((week) => week.item_count).join(", ")} (oldest first)`
      }
    >
      {weeks.map((week, index) => {
        const barHeight = Math.max(2, Math.round((week.item_count / highest) * HEIGHT));
        return (
          <rect
            key={week.week_start}
            x={index * (BAR_WIDTH + BAR_GAP)}
            y={HEIGHT - barHeight}
            width={BAR_WIDTH}
            height={barHeight}
            rx={2}
            className={
              index === weeks.length - 1
                ? "fill-zinc-900 dark:fill-zinc-100"
                : "fill-zinc-300 dark:fill-zinc-700"
            }
          />
        );
      })}
    </svg>
  );
}
