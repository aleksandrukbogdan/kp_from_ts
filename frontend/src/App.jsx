// src/App.jsx
import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';

// Импортируем страницы
import Portal from './Portal';
import AgentKP from './AgentKP';
import Login from './Login';

// Material 3 Theme с оранжевой палитрой
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#FF6B00',
      light: '#FF8C3F',
      dark: '#CC5600',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#FFCC80',
      light: '#FFE0B2',
      dark: '#FFB74D',
    },
    background: {
      default: '#F8F9FA',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#212121',
      secondary: '#757575',
    },
    error: {
      main: '#D32F2F',
    },
    success: {
      main: '#388E3C',
    },
    divider: 'rgba(0, 0, 0, 0.08)',
  },
  shape: {
    borderRadius: 16,
  },
  typography: {
    fontFamily: '"Onest", -apple-system, BlinkMacSystemFont, sans-serif',
    h3: {
      fontWeight: 600,
      letterSpacing: '-0.02em',
    },
    h4: {
      fontWeight: 600,
      letterSpacing: '-0.01em',
    },
    h5: {
      fontWeight: 600,
      color: '#212121',
    },
    h6: {
      fontWeight: 600,
      color: '#212121',
    },
    button: {
      fontWeight: 500,
    },
  },
  shadows: [
    'none',
    '0px 1px 3px rgba(0, 0, 0, 0.04)',
    '0px 2px 6px rgba(0, 0, 0, 0.06)',
    '0px 4px 12px rgba(0, 0, 0, 0.08)',
    '0px 6px 16px rgba(0, 0, 0, 0.1)',
    '0px 8px 20px rgba(0, 0, 0, 0.12)',
    '0px 10px 24px rgba(0, 0, 0, 0.14)',
    ...Array(18).fill('0px 10px 24px rgba(0, 0, 0, 0.14)'),
  ],
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 24,
          fontWeight: 500,
          padding: '10px 24px',
        },
        contained: {
          boxShadow: '0px 2px 8px rgba(255, 107, 0, 0.3)',
          '&:hover': {
            boxShadow: '0px 4px 16px rgba(255, 107, 0, 0.4)',
          },
        },
        outlined: {
          borderWidth: 2,
          '&:hover': {
            borderWidth: 2,
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          boxShadow: '0px 4px 20px rgba(0, 0, 0, 0.05)',
          transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 16,
        },
        elevation1: {
          boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.06)',
        },
        elevation2: {
          boxShadow: '0px 4px 16px rgba(0, 0, 0, 0.08)',
        },
        elevation3: {
          boxShadow: '0px 6px 24px rgba(0, 0, 0, 0.1)',
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 12,
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: '#FF6B00',
            },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
              borderColor: '#FF6B00',
              borderWidth: 2,
            },
          },
          '& .MuiInputLabel-root.Mui-focused': {
            color: '#FF6B00',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
        },
        colorPrimary: {
          backgroundColor: '#FF6B00',
          color: '#FFFFFF',
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 28,
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-head': {
            fontWeight: 600,
            backgroundColor: '#F8F9FA',
            color: '#757575',
          },
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          '&:hover': {
            backgroundColor: 'rgba(255, 107, 0, 0.04)',
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          '&:hover': {
            backgroundColor: 'rgba(255, 107, 0, 0.08)',
          },
        },
      },
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />

      {/* Обертка Роутера */}
      <BrowserRouter>
        <Routes>
          {/* Страница авторизации */}
          <Route path="/login" element={<Login />} />

          {/* Главная страница -> Портал */}
          <Route path="/" element={<Portal />} />

          {/* Страница приложения -> Агент КП (с встроенной историей) */}
          <Route path="/agent-kp" element={<AgentKP />} />
        </Routes>
      </BrowserRouter>

    </ThemeProvider>
  );
}

export default App;