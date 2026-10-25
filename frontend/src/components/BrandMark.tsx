import { Link } from 'react-router-dom'

type Props = {
  to?: string
}

export default function BrandMark({ to = '/' }: Props) {
  return (
    <Link to={to} className="brand-mark" aria-label="万象影界 VISTAVERSE">
      <img src="/logo.svg" alt="万象影界" className="brand-logo" width={28} height={28} />
      <span className="brand-word">
        <strong>万象影界</strong>
        <small>VISTAVERSE</small>
      </span>
    </Link>
  )
}
