
interface LoadingSpinnerProps {
  message?: string
  isDark?: boolean
}

export default function LoadingSpinner({ message = 'Analyzing product...', isDark = false }: LoadingSpinnerProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      gap: '24px',
      background: isDark ? '#000' : '#f5f5f7',
      padding: '24px',
    }}>
      <div style={{
        width: '72px',
        height: '72px',
        borderRadius: '50%',
        border: `4px solid ${isDark ? '#3a3a3c' : '#e5e5ea'}`,
        borderTopColor: '#34c759',
        animation: 'spin 0.9s linear infinite',
      }} />

      <div style={{ textAlign: 'center' }}>
        <p style={{
          fontSize: '18px',
          fontWeight: '600',
          color: isDark ? '#f2f2f7' : '#1c1c1e',
          marginBottom: '8px',
        }}>
          {message}
        </p>
        <p style={{
          fontSize: '14px',
          color: '#8e8e93',
        }}>
          Our AI is checking ingredients and safety data
        </p>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
