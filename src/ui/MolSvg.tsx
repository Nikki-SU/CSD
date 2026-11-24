// 结构式示意：代码内合成，公库零数据。等比缩放进框，不裁剪。
type Props = {
  color?: string
  variant?: 0 | 1 | 2 | 3
  className?: string
}

export default function MolSvg({ color = '#185fa5', variant = 0, className }: Props) {
  const shapes = [
    <polygon key="hex" points="50,10 82,28 82,64 50,82 18,64 18,28" />,
    <rect key="sq" x="18" y="18" width="64" height="64" rx="6" />,
    <polygon key="dia" points="50,10 88,46 50,82 12,46" />,
    <circle key="ci" cx="50" cy="46" r="30" />,
  ]
  return (
    <svg
      className={className}
      viewBox="0 0 100 92"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="结构式示意"
    >
      <g fill="none" stroke={color} strokeWidth="2">
        {shapes[variant]}
      </g>
    </svg>
  )
}
