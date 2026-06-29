const COLORS = [
    "bg-rose-500",
    "bg-orange-500",
    "bg-amber-500",
    "bg-emerald-500",
    "bg-sky-500",
    "bg-indigo-500",
    "bg-fuchsia-500",
];

export default function Avatar({
    name,
    id,
    size = 40,
}: {
    name: string | null;
    id: number;
    size?: number;
}) {
    const initial = (name?.trim()?.[0] ?? "?").toUpperCase();
    const color = COLORS[id % COLORS.length];
    return (
        <div
            className={`flex shrink-0 items-center justify-center rounded-full font-semibold text-white ${color}`}
            style={{ width: size, height: size, fontSize: size * 0.42 }}
        >
            {initial}
        </div>
    );
}
