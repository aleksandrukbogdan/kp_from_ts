// src/Login.jsx
import React, { useState } from 'react';
import {
    Box, Paper, Typography, TextField, Button, Alert, CircularProgress
} from '@mui/material';
import { Login as LoginIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { config } from './config';

const API_URL = config.API_URL;

export default function Login() {
    const navigate = useNavigate();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const res = await axios.post(`${API_URL}/login`, {
                username,
                password
            }, { withCredentials: true });

            if (res.data.success) {
                // Сохраняем пользователя в cookie (сервер уже установит токен)
                document.cookie = `portal_user=${encodeURIComponent(username)}; path=/; max-age=86400`;
                document.cookie = `portal_auth_token=${res.data.token}; path=/; max-age=86400`;
                navigate('/');
            }
        } catch (err) {
            if (err.response?.status === 401) {
                setError('Неверное имя пользователя или пароль');
            } else {
                setError('Ошибка соединения с сервером');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Box
            sx={{
                minHeight: '100vh',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'background.default',
                px: 2,
            }}
        >
            {/* Logo */}
            <Box
                component="img"
                src="/logo.svg"
                alt="НИР-центр"
                sx={{ height: 48, mb: 4 }}
            />

            {/* Login Card */}
            <Paper
                elevation={0}
                sx={{
                    p: 5,
                    width: '100%',
                    maxWidth: 420,
                    borderRadius: 4,
                    boxShadow: '0px 8px 40px rgba(0, 0, 0, 0.08)',
                }}
            >
                <Typography
                    variant="h5"
                    fontWeight={600}
                    textAlign="center"
                    gutterBottom
                    sx={{ mb: 1 }}
                >
                    Добро пожаловать
                </Typography>
                <Typography
                    variant="body2"
                    color="text.secondary"
                    textAlign="center"
                    sx={{ mb: 4 }}
                >
                    Войдите в систему для доступа к сервисам
                </Typography>

                {error && (
                    <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
                        {error}
                    </Alert>
                )}

                <Box component="form" onSubmit={handleSubmit}>
                    <TextField
                        fullWidth
                        label="Имя пользователя"
                        variant="outlined"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        required
                        sx={{ mb: 2.5 }}
                        autoComplete="username"
                        autoFocus
                    />
                    <TextField
                        fullWidth
                        label="Пароль"
                        type="password"
                        variant="outlined"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        sx={{ mb: 3 }}
                        autoComplete="current-password"
                    />
                    <Button
                        type="submit"
                        fullWidth
                        variant="contained"
                        size="large"
                        disabled={loading || !username || !password}
                        startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <LoginIcon />}
                        sx={{ py: 1.5 }}
                    >
                        {loading ? 'Вход...' : 'Войти'}
                    </Button>
                </Box>
            </Paper>

            {/* Footer */}
            <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 4 }}
            >
                © 2026 НИР-центр
            </Typography>
        </Box>
    );
}
