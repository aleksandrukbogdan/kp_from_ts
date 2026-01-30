// src/Portal.jsx
import React, { useState, useEffect } from 'react';
import {
    Container, Typography, Grid, Card, CardContent, CardActionArea,
    Box, Chip, AppBar, Toolbar, Button, Avatar, Menu, MenuItem,
    IconButton, Divider
} from '@mui/material';
import { Description, Chat, Mic, VisibilityOff, CompareArrows, Logout, Person } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { config } from './config';

// Функция для получения имени пользователя из cookie
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
    return null;
}

export default function Portal() {
    const navigate = useNavigate();
    const [username, setUsername] = useState('');
    const [anchorEl, setAnchorEl] = useState(null);

    useEffect(() => {
        const user = getCookie('portal_user');
        if (user) {
            setUsername(user);
        } else {
            // Если пользователь не авторизован - перенаправляем на логин
            navigate('/login');
        }
    }, [navigate]);

    const handleMenuOpen = (event) => {
        setAnchorEl(event.currentTarget);
    };

    const handleMenuClose = () => {
        setAnchorEl(null);
    };

    const handleLogout = () => {
        // Очищаем куки и перенаправляем на страницу логина
        document.cookie = 'portal_auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'portal_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        navigate('/login');
    };

    const apps = [
        {
            title: "Агент КП",
            desc: "Генерация коммерческих предложений по ТЗ",
            icon: <Description fontSize="large" sx={{ color: 'white' }} />,
            gradient: 'linear-gradient(135deg, #FF6B00 0%, #FF8C3F 100%)',
            path: "/agent-kp",
            active: true,
            external: false
        },
        {
            title: "RAG",
            desc: "Задавайте вопросы по своим документам",
            icon: <Chat fontSize="large" sx={{ color: 'white' }} />,
            gradient: 'linear-gradient(135deg, #1E3A5F 0%, #3D5A80 100%)',
            path: config.RAG_BOT_URL,
            active: true,
            external: true
        },
        {
            title: "ВКС резюмирование",
            desc: "Расшифровка и итоги встреч",
            icon: <Mic fontSize="large" sx={{ color: 'white' }} />,
            gradient: 'linear-gradient(135deg, #388E3C 0%, #66BB6A 100%)',
            path: config.VKS_SUMMARY_URL,
            active: true,
            external: true
        },
        {
            title: "Обезличиватель",
            desc: "Скрытие чувствительных данных",
            icon: <VisibilityOff fontSize="large" sx={{ color: 'white' }} />,
            gradient: 'linear-gradient(135deg, #757575 0%, #9E9E9E 100%)',
            path: config.ANONYMIZER_URL,
            active: true,
            external: true
        },
        {
            title: "СравнениеДок",
            desc: "Сравнение документов",
            icon: <CompareArrows fontSize="large" sx={{ color: 'white' }} />,
            gradient: 'linear-gradient(135deg, #7B1FA2 0%, #AB47BC 100%)',
            path: config.DOC_COMPARE_URL,
            active: true,
            external: true
        }
    ];

    const handleCardClick = (app) => {
        if (!app.active) return;
        if (app.external) {
            window.open(app.path, '_blank');
        } else {
            navigate(app.path);
        }
    };

    return (
        <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
            {/* Header */}
            <AppBar
                position="static"
                elevation={0}
                sx={{
                    backgroundColor: 'white',
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                }}
            >
                <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 4 } }}>
                    {/* Logo */}
                    <Box
                        component="img"
                        src="/logo.svg"
                        alt="НИР-центр"
                        sx={{ height: 32 }}
                    />

                    {/* User Menu */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <IconButton onClick={handleMenuOpen} sx={{ gap: 1, borderRadius: 2, px: 1.5 }}>
                            <Avatar
                                sx={{
                                    width: 32,
                                    height: 32,
                                    bgcolor: 'primary.main',
                                    fontSize: '0.875rem',
                                }}
                            >
                                {username ? username.charAt(0).toUpperCase() : <Person />}
                            </Avatar>
                            <Typography
                                variant="body2"
                                sx={{
                                    color: 'text.primary',
                                    fontWeight: 500,
                                    display: { xs: 'none', sm: 'block' }
                                }}
                            >
                                {username || 'Пользователь'}
                            </Typography>
                        </IconButton>

                        <Menu
                            anchorEl={anchorEl}
                            open={Boolean(anchorEl)}
                            onClose={handleMenuClose}
                            transformOrigin={{ horizontal: 'right', vertical: 'top' }}
                            anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
                            PaperProps={{
                                sx: { mt: 1, minWidth: 180 }
                            }}
                        >
                            <MenuItem disabled>
                                <Typography variant="body2" color="text.secondary">
                                    {username}
                                </Typography>
                            </MenuItem>
                            <Divider />
                            <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
                                <Logout fontSize="small" sx={{ mr: 1.5 }} />
                                Выйти
                            </MenuItem>
                        </Menu>
                    </Box>
                </Toolbar>
            </AppBar>

            {/* Main Content */}
            <Container maxWidth="lg" sx={{ py: 8, flex: 1 }}>
                <Box mb={6} textAlign="center">
                    <Typography
                        variant="h3"
                        component="h1"
                        fontWeight="bold"
                        gutterBottom
                        sx={{ color: 'text.primary' }}
                    >
                        AI Platform{' '}
                        <Box component="span" sx={{ color: 'primary.main' }}>
                            НИР-центр
                        </Box>
                    </Typography>
                    <Typography variant="h6" color="text.secondary" fontWeight={400}>
                        Единое пространство интеллектуальных сервисов
                    </Typography>
                </Box>

                <Grid container spacing={3}>
                    {apps.map((app, index) => (
                        <Grid item xs={12} sm={6} md={3} key={index}>
                            <Card
                                sx={{
                                    height: '100%',
                                    position: 'relative',
                                    cursor: app.active ? 'pointer' : 'default',
                                    opacity: app.active ? 1 : 0.7,
                                    '&:hover': app.active ? {
                                        transform: 'translateY(-4px)',
                                        boxShadow: '0px 8px 32px rgba(0, 0, 0, 0.12)',
                                    } : {},
                                }}
                            >
                                <CardActionArea
                                    onClick={() => handleCardClick(app)}
                                    disabled={!app.active}
                                    sx={{ height: '100%', p: 2.5 }}
                                >
                                    <CardContent sx={{ p: 0 }}>
                                        {/* Icon Box */}
                                        <Box
                                            sx={{
                                                width: 56,
                                                height: 56,
                                                borderRadius: 3,
                                                background: app.gradient,
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                mb: 2.5,
                                                boxShadow: app.active
                                                    ? '0px 4px 12px rgba(0, 0, 0, 0.15)'
                                                    : 'none',
                                            }}
                                        >
                                            {app.icon}
                                        </Box>

                                        {/* Title */}
                                        <Typography
                                            variant="h6"
                                            component="div"
                                            fontWeight={600}
                                            gutterBottom
                                            sx={{ fontSize: '1.1rem' }}
                                        >
                                            {app.title}
                                        </Typography>

                                        {/* Description */}
                                        <Typography
                                            variant="body2"
                                            color="text.secondary"
                                            sx={{ mb: app.active ? 0 : 2, lineHeight: 1.5 }}
                                        >
                                            {app.desc}
                                        </Typography>

                                        {/* Coming Soon Chip */}
                                        {!app.active && (
                                            <Chip
                                                label="Скоро"
                                                color="primary"
                                                size="small"
                                                sx={{ mt: 1 }}
                                            />
                                        )}
                                    </CardContent>
                                </CardActionArea>
                            </Card>
                        </Grid>
                    ))}
                </Grid>
            </Container>

            {/* Footer */}
            <Box
                component="footer"
                sx={{
                    py: 3,
                    textAlign: 'center',
                    borderTop: '1px solid',
                    borderColor: 'divider',
                    backgroundColor: 'background.paper',
                }}
            >
                <Typography variant="body2" color="text.secondary">
                    © 2026 НИР-центр. Все права защищены.
                </Typography>
            </Box>
        </Box>
    );
}