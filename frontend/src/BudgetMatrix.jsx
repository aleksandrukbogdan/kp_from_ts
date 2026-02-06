import React, { useState, useMemo, useCallback } from 'react';
import {
    Box, Paper, Typography, TextField, IconButton, Tooltip, Chip,
    Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
    Button, Dialog, DialogTitle, DialogContent, DialogActions,
    Slider, Collapse, Alert, Divider
} from '@mui/material';
import {
    Add, Delete, Warning, TrendingUp, CompareArrows,
    ExpandMore, ExpandLess, Timeline
} from '@mui/icons-material';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';

// Material 3 harmonized palette with #FF6B00
const ROLE_COLORS = [
    '#FF6B00', // Primary Orange
    '#455A64', // Slate (грифельный)
    '#00796B', // Teal (тиловый)
    '#5D4037', // Brown (тёплый нейтральный)
    '#607D8B', // Blue-grey (приглушенный синий)
    '#BF360C', // Deep Orange (тёмно-кирпичный)
    '#37474F', // Dark Slate
    '#004D40', // Dark Teal
];

// Часов в неделе для расчёта длительности Gantt
const HOURS_PER_WEEK = 40;

// Получить цвет ячейки по количеству часов
const getCellColor = (hours) => {
    if (hours === 0) return 'transparent';
    if (hours <= 20) return 'rgba(76, 175, 80, 0.15)'; // Green
    if (hours <= 40) return 'rgba(255, 193, 7, 0.2)';  // Yellow
    if (hours <= 60) return 'rgba(255, 152, 0, 0.2)';  // Orange
    return 'rgba(244, 67, 54, 0.2)';                    // Red
};

// Получить цвет текста по часам
const getCellTextColor = (hours, isModified) => {
    if (isModified) return '#1976D2';
    if (hours === 0) return '#9E9E9E';
    if (hours <= 20) return '#2E7D32';
    if (hours <= 40) return '#F57C00';
    if (hours <= 60) return '#E65100';
    return '#C62828';
};

export default function BudgetMatrix({
    stages,
    setStages,
    roles,
    setRoles,
    budgetMatrix,
    setBudgetMatrix,
    userModified,
    setUserModified,
    suggestedHours = {},
    onAddStage,
    onAddRole,
    onDeleteStage,
    onDeleteRole,
}) {
    // Локальные состояния
    const [riskCoefficients, setRiskCoefficients] = useState({});
    const [showComparison, setShowComparison] = useState(false);
    const [showGantt, setShowGantt] = useState(false);
    const [showStats, setShowStats] = useState(true);
    const [editingRisk, setEditingRisk] = useState(null);

    // Gantt: смещение начала каждого этапа (в неделях)
    const [stageOffsets, setStageOffsets] = useState({});
    // Для подсветки при hover
    const [hoveredStage, setHoveredStage] = useState(null);

    // Диалоги
    const [openRoleDialog, setOpenRoleDialog] = useState(false);
    const [openStageDialog, setOpenStageDialog] = useState(false);
    const [newRoleName, setNewRoleName] = useState('');
    const [newRoleRate, setNewRoleRate] = useState(2500);
    const [newStageName, setNewStageName] = useState('');

    // Обработчик изменения часов
    const handleHourChange = useCallback((stage, role, value) => {
        const val = parseInt(value) || 0;
        setBudgetMatrix(prev => ({
            ...prev,
            [stage]: { ...prev[stage], [role]: val }
        }));
        setUserModified(prev => ({
            ...prev,
            [stage]: { ...prev[stage], [role]: true }
        }));
    }, [setBudgetMatrix, setUserModified]);

    // Обработчик изменения риска
    const handleRiskChange = useCallback((stage, value) => {
        setRiskCoefficients(prev => ({ ...prev, [stage]: value }));
    }, []);

    // Добавление роли
    const handleAddRole = useCallback(() => {
        if (newRoleName && !roles[newRoleName]) {
            if (onAddRole) {
                onAddRole(newRoleName, Number(newRoleRate));
            } else {
                setRoles(prev => ({ ...prev, [newRoleName]: Number(newRoleRate) }));
            }
            setOpenRoleDialog(false);
            setNewRoleName('');
            setNewRoleRate(2500);
        }
    }, [newRoleName, newRoleRate, roles, onAddRole, setRoles]);

    // Добавление этапа
    const handleAddStage = useCallback(() => {
        if (newStageName && !stages.includes(newStageName)) {
            if (onAddStage) {
                onAddStage(newStageName);
            } else {
                setStages(prev => [...prev, newStageName]);
                setBudgetMatrix(prev => ({ ...prev, [newStageName]: {} }));
            }
            setOpenStageDialog(false);
            setNewStageName('');
        }
    }, [newStageName, stages, onAddStage, setStages, setBudgetMatrix]);

    // Вычисления
    const calculations = useMemo(() => {
        const roleHours = {};
        const roleCosts = {};
        const stageHours = {};
        const stageCosts = {};
        let totalHours = 0;
        let totalCost = 0;
        let totalWithRisk = 0;

        Object.keys(roles).forEach(role => {
            roleHours[role] = 0;
            roleCosts[role] = 0;
        });

        stages.forEach(stage => {
            stageHours[stage] = 0;
            stageCosts[stage] = 0;
            const risk = riskCoefficients[stage] || 1;

            Object.keys(roles).forEach(role => {
                const hours = budgetMatrix[stage]?.[role] || 0;
                const rate = roles[role];
                const cost = hours * rate;
                const costWithRisk = cost * risk;

                roleHours[role] += hours;
                roleCosts[role] += cost;
                stageHours[stage] += hours;
                stageCosts[stage] += cost;
                totalHours += hours;
                totalCost += cost;
                totalWithRisk += costWithRisk;
            });
        });

        return { roleHours, roleCosts, stageHours, stageCosts, totalHours, totalCost, totalWithRisk };
    }, [stages, roles, budgetMatrix, riskCoefficients]);

    // Данные для диаграмм
    const pieData = useMemo(() => {
        return Object.entries(calculations.roleHours)
            .filter(([_, hours]) => hours > 0)
            .map(([role, hours], idx) => ({
                name: role,
                value: hours,
                color: ROLE_COLORS[idx % ROLE_COLORS.length]
            }));
    }, [calculations.roleHours]);

    const ganttData = useMemo(() => {
        let cumulativeOffset = 0;
        return stages.map((stage, idx) => {
            const stageRoleHours = budgetMatrix[stage] || {};
            const totalHours = calculations.stageHours[stage] || 0;

            // Option C: Рассчитываем длительность на основе параллельности ролей
            // Ищем максимальные часы среди всех ролей на этапе
            const maxRoleHours = Math.max(...Object.values(stageRoleHours), 0);
            // Длительность = макс. часы / часов в неделю (округляем вверх, минимум 1)
            const duration = Math.max(1, Math.ceil(maxRoleHours / HOURS_PER_WEEK));

            // Используем сохранённое смещение или кумулятивное
            const startOffset = stageOffsets[stage] ?? cumulativeOffset;
            cumulativeOffset = startOffset + duration;

            return {
                name: stage,
                hours: totalHours,
                maxRoleHours,
                duration,
                startOffset,
                endOffset: startOffset + duration,
                risk: riskCoefficients[stage] || 1,
                fill: '#78909C', // Neutral blue-grey
            };
        });
    }, [stages, budgetMatrix, calculations.stageHours, stageOffsets, riskCoefficients]);

    // Максимальная длина шкалы (для X-axis)
    const maxWeeks = useMemo(() => {
        return Math.max(...ganttData.map(d => d.endOffset), 4);
    }, [ganttData]);

    // Обработчик перетаскивания этапов в Gantt
    const handleStageOffsetChange = useCallback((stageName, newOffset) => {
        setStageOffsets(prev => ({
            ...prev,
            [stageName]: Math.max(0, Math.round(newOffset))
        }));
    }, []);

    // Сравнение с AI
    const getDiff = useCallback((stage, role) => {
        const current = budgetMatrix[stage]?.[role] || 0;
        const suggested = suggestedHours[stage]?.[role] || 0;
        return current - suggested;
    }, [budgetMatrix, suggestedHours]);

    return (
        <Box>
            {/* Header с кнопками */}
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={1}>
                <Typography variant="h6" fontWeight={600}>
                    Матрица трудозатрат
                </Typography>
                <Box display="flex" gap={1} alignItems="center">
                    {/* Segmented Button style toggles */}
                    <Chip
                        label="Сравнить с AI"
                        icon={<CompareArrows sx={{ fontSize: 16 }} />}
                        onClick={() => setShowComparison(!showComparison)}
                        variant={showComparison ? 'filled' : 'outlined'}
                        size="small"
                        sx={{
                            bgcolor: showComparison ? '#FF6B00' : 'transparent',
                            color: showComparison ? 'white' : 'text.primary',
                            borderColor: showComparison ? '#FF6B00' : 'divider',
                            '&:hover': { bgcolor: showComparison ? '#E65100' : 'action.hover' },
                            '& .MuiChip-icon': { color: showComparison ? 'white' : 'text.secondary' }
                        }}
                    />
                    <Chip
                        label="Gantt"
                        icon={<Timeline sx={{ fontSize: 16 }} />}
                        onClick={() => setShowGantt(!showGantt)}
                        variant={showGantt ? 'filled' : 'outlined'}
                        size="small"
                        sx={{
                            bgcolor: showGantt ? '#FF6B00' : 'transparent',
                            color: showGantt ? 'white' : 'text.primary',
                            borderColor: showGantt ? '#FF6B00' : 'divider',
                            '&:hover': { bgcolor: showGantt ? '#E65100' : 'action.hover' },
                            '& .MuiChip-icon': { color: showGantt ? 'white' : 'text.secondary' }
                        }}
                    />

                    <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

                    {/* Filled Tonal Buttons */}
                    <Button
                        startIcon={<Add />}
                        onClick={() => setOpenStageDialog(true)}
                        size="small"
                        sx={{
                            bgcolor: '#FFDCC2',
                            color: '#331200',
                            fontWeight: 500,
                            '&:hover': { bgcolor: '#FFCC99' },
                            textTransform: 'none',
                        }}
                    >
                        Этап
                    </Button>
                    <Button
                        startIcon={<Add />}
                        onClick={() => setOpenRoleDialog(true)}
                        size="small"
                        sx={{
                            bgcolor: '#FFDCC2',
                            color: '#331200',
                            fontWeight: 500,
                            '&:hover': { bgcolor: '#FFCC99' },
                            textTransform: 'none',
                        }}
                    >
                        Роль
                    </Button>
                </Box>
            </Box>

            {/* Gantt view - Material 3 Timeline style */}
            <Collapse in={showGantt}>
                <Paper
                    elevation={0}
                    sx={{
                        p: 3,
                        mb: 3,
                        bgcolor: 'background.paper',
                        borderRadius: 6, // 24px Material 3
                        border: '1px solid',
                        borderColor: 'divider',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                    }}
                >
                    <Box display="flex" alignItems="center" gap={1} mb={3}>
                        <Timeline sx={{ color: '#FF6B00' }} />
                        <Typography variant="subtitle1" fontWeight={600}>
                            Диаграмма Ганта (Недели)
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                            Перетащите бары для изменения расписания
                        </Typography>
                    </Box>

                    {/* Gantt Timeline */}
                    <Box sx={{ overflowX: 'auto', pb: 2 }}>
                        {/* Шкала недель */}
                        <Box display="flex" mb={1} ml="200px" borderBottom="1px solid #E0E0E0">
                            {Array.from({ length: maxWeeks + 1 }, (_, i) => (
                                <Box
                                    key={i}
                                    sx={{
                                        width: 50,
                                        flexShrink: 0,
                                        textAlign: 'center',
                                        borderLeft: i === 0 ? 'none' : '1px solid #E0E0E0',
                                        pb: 0.5,
                                    }}
                                >
                                    <Typography variant="caption" color="text.secondary" fontWeight={500}>
                                        {i + 1}
                                    </Typography>
                                </Box>
                            ))}
                            <Typography variant="caption" color="text.secondary" sx={{ ml: 1, alignSelf: 'center' }}>
                                нед.
                            </Typography>
                        </Box>

                        {/* Бары этапов */}
                        {ganttData.map((item, idx) => (
                            <Box
                                key={item.name}
                                display="flex"
                                alignItems="center"
                                mb={0.5}
                                onMouseEnter={() => setHoveredStage(item.name)}
                                onMouseLeave={() => setHoveredStage(null)}
                                sx={{
                                    minHeight: 44,
                                    borderRadius: 2,
                                    bgcolor: hoveredStage === item.name ? 'rgba(255, 107, 0, 0.04)' : 'transparent',
                                    transition: 'background-color 0.2s',
                                }}
                            >
                                {/* Название этапа (фиксированная ширина) */}
                                <Box sx={{
                                    width: 200,
                                    flexShrink: 0,
                                    pr: 2,
                                }}>
                                    <Tooltip title={item.name} placement="top-start">
                                        <Typography
                                            variant="body2"
                                            noWrap
                                            fontWeight={hoveredStage === item.name ? 600 : 500}
                                            sx={{
                                                color: hoveredStage === item.name ? '#FF6B00' : 'text.primary',
                                                cursor: 'default',
                                            }}
                                        >
                                            {item.name}
                                        </Typography>
                                    </Tooltip>
                                    <Typography variant="caption" color="text.secondary">
                                        {item.hours}ч · {item.duration} нед.
                                    </Typography>
                                </Box>

                                {/* Бар (с drag) */}
                                <Box
                                    sx={{
                                        ml: `${item.startOffset * 50}px`,
                                        width: `${Math.max(item.duration * 50 - 4, 20)}px`,
                                        height: 28,
                                        bgcolor: hoveredStage === item.name ? '#FF6B00' : item.fill,
                                        borderRadius: '4px 8px 8px 4px',
                                        cursor: 'grab',
                                        transition: 'background-color 0.2s, transform 0.1s, box-shadow 0.2s',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        boxShadow: hoveredStage === item.name ? '0 2px 8px rgba(255, 107, 0, 0.3)' : 'none',
                                        '&:hover': {
                                            transform: 'scaleY(1.08)'
                                        },
                                        '&:active': { cursor: 'grabbing' }
                                    }}
                                    draggable
                                    onDragStart={(e) => {
                                        e.dataTransfer.setData('stageName', item.name);
                                        e.dataTransfer.setData('startOffset', String(item.startOffset));
                                        e.dataTransfer.effectAllowed = 'move';
                                    }}
                                    onDragEnd={(e) => {
                                        // Рассчитываем новое смещение на основе позиции
                                        const dropX = e.clientX;
                                        const container = e.target.closest('.MuiBox-root')?.parentElement;
                                        if (container) {
                                            const rect = container.getBoundingClientRect();
                                            const relativeX = dropX - rect.left - 200; // 200px = ширина лейблов
                                            const newOffset = Math.round(relativeX / 50);
                                            handleStageOffsetChange(item.name, newOffset);
                                        }
                                    }}
                                >
                                    {item.duration > 1 && (
                                        <Typography
                                            variant="caption"
                                            sx={{
                                                color: 'white',
                                                fontWeight: 600,
                                                fontSize: '0.65rem',
                                                textShadow: '0 1px 2px rgba(0,0,0,0.3)'
                                            }}
                                        >
                                            {item.duration}н
                                        </Typography>
                                    )}
                                </Box>
                            </Box>
                        ))}
                    </Box>
                </Paper>
            </Collapse>

            {/* Main Table */}
            <TableContainer sx={{ borderRadius: 2, border: '1px solid', borderColor: 'divider', mb: 2 }}>
                <Table size="small">
                    <TableHead>
                        <TableRow sx={{ bgcolor: 'grey.50' }}>
                            <TableCell sx={{ minWidth: 180, fontWeight: 600 }}>
                                Этапы работ
                            </TableCell>
                            {Object.keys(roles).map((role, idx) => (
                                <TableCell key={role} align="center" sx={{ minWidth: 100 }}>
                                    <Box display="flex" flexDirection="column" alignItems="center">
                                        <Box display="flex" alignItems="center" gap={0.5}>
                                            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: ROLE_COLORS[idx % ROLE_COLORS.length] }} />
                                            <Typography variant="body2" fontWeight={600}>{role}</Typography>
                                            <IconButton
                                                size="small"
                                                onClick={() => onDeleteRole ? onDeleteRole(role) : null}
                                                sx={{ color: 'text.secondary', p: 0.25 }}
                                            >
                                                <Delete sx={{ fontSize: 14 }} />
                                            </IconButton>
                                        </Box>
                                        <TextField
                                            type="number"
                                            variant="standard"
                                            size="small"
                                            value={roles[role]}
                                            onChange={(e) => setRoles(prev => ({ ...prev, [role]: parseInt(e.target.value) || 0 }))}
                                            InputProps={{
                                                disableUnderline: true,
                                                endAdornment: <Typography variant="caption" color="text.disabled">₽/ч</Typography>,
                                                inputProps: { style: { textAlign: 'center', width: 40, fontSize: '0.7rem' } }
                                            }}
                                            sx={{ '& input': { bgcolor: 'grey.100', borderRadius: 0.5, p: 0.25 } }}
                                        />
                                    </Box>
                                </TableCell>
                            ))}
                            {/* Риск колонка */}
                            <TableCell align="center" sx={{ minWidth: 80, bgcolor: 'warning.50' }}>
                                <Tooltip title="Коэффициент риска для этапа">
                                    <Box display="flex" alignItems="center" justifyContent="center" gap={0.5}>
                                        <Warning fontSize="small" sx={{ color: 'warning.main' }} />
                                        <Typography variant="caption" fontWeight={600}>Риск</Typography>
                                    </Box>
                                </Tooltip>
                            </TableCell>
                            {/* Итого по строке */}
                            <TableCell align="center" sx={{ minWidth: 90, bgcolor: 'primary.50' }}>
                                <Typography variant="body2" fontWeight={600}>Итого</Typography>
                            </TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {stages.map(stage => {
                            const risk = riskCoefficients[stage] || 1;
                            const stageTotal = calculations.stageHours[stage] || 0;
                            const stageCost = calculations.stageCosts[stage] || 0;

                            return (
                                <TableRow key={stage} hover>
                                    <TableCell sx={{ fontWeight: 500 }}>
                                        <Box display="flex" alignItems="center" justifyContent="space-between">
                                            <Typography variant="body2">{stage}</Typography>
                                            <IconButton
                                                size="small"
                                                onClick={() => onDeleteStage ? onDeleteStage(stage) : null}
                                                sx={{ color: 'text.secondary', opacity: 0.5, '&:hover': { opacity: 1 } }}
                                            >
                                                <Delete fontSize="small" />
                                            </IconButton>
                                        </Box>
                                    </TableCell>
                                    {Object.keys(roles).map(role => {
                                        const hours = budgetMatrix[stage]?.[role] || 0;
                                        const isModified = userModified?.[stage]?.[role];
                                        const diff = showComparison ? getDiff(stage, role) : 0;

                                        return (
                                            <TableCell
                                                key={role}
                                                align="center"
                                                sx={{ bgcolor: getCellColor(hours), position: 'relative' }}
                                            >
                                                <TextField
                                                    type="number"
                                                    variant="standard"
                                                    value={hours}
                                                    onChange={(e) => handleHourChange(stage, role, e.target.value)}
                                                    InputProps={{
                                                        disableUnderline: true,
                                                        inputProps: {
                                                            style: {
                                                                textAlign: 'center',
                                                                color: getCellTextColor(hours, isModified),
                                                                fontWeight: isModified ? 600 : 400,
                                                                fontStyle: isModified ? 'normal' : 'italic'
                                                            },
                                                            min: 0
                                                        }
                                                    }}
                                                    sx={{ width: 50 }}
                                                />
                                                {/* Diff indicator */}
                                                {showComparison && diff !== 0 && (
                                                    <Chip
                                                        size="small"
                                                        label={diff > 0 ? `+${diff}` : diff}
                                                        sx={{
                                                            position: 'absolute',
                                                            top: 2,
                                                            right: 2,
                                                            height: 16,
                                                            fontSize: '0.6rem',
                                                            bgcolor: diff > 0 ? 'error.100' : 'success.100',
                                                            color: diff > 0 ? 'error.dark' : 'success.dark'
                                                        }}
                                                    />
                                                )}
                                            </TableCell>
                                        );
                                    })}
                                    {/* Risk cell */}
                                    <TableCell align="center" sx={{ bgcolor: risk > 1 ? 'warning.50' : 'transparent' }}>
                                        {editingRisk === stage ? (
                                            <Box sx={{ px: 1 }}>
                                                <Slider
                                                    value={risk}
                                                    onChange={(e, v) => handleRiskChange(stage, v)}
                                                    onChangeCommitted={() => setEditingRisk(null)}
                                                    min={1}
                                                    max={2}
                                                    step={0.1}
                                                    size="small"
                                                    valueLabelDisplay="auto"
                                                    valueLabelFormat={(v) => `×${v.toFixed(1)}`}
                                                />
                                            </Box>
                                        ) : (
                                            <Chip
                                                size="small"
                                                label={`×${risk.toFixed(1)}`}
                                                onClick={() => setEditingRisk(stage)}
                                                color={risk > 1 ? 'warning' : 'default'}
                                                variant={risk > 1 ? 'filled' : 'outlined'}
                                                sx={{ cursor: 'pointer', fontSize: '0.75rem' }}
                                            />
                                        )}
                                    </TableCell>
                                    {/* Stage total */}
                                    <TableCell align="center" sx={{ bgcolor: 'grey.50' }}>
                                        <Typography variant="body2" fontWeight={600}>{stageTotal} ч</Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {(stageCost * risk).toLocaleString('ru-RU')} ₽
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                        {/* Footer row - totals by role */}
                        <TableRow sx={{ bgcolor: 'grey.100' }}>
                            <TableCell sx={{ fontWeight: 700 }}>ИТОГО</TableCell>
                            {Object.keys(roles).map(role => (
                                <TableCell key={role} align="center">
                                    <Typography variant="body2" fontWeight={600}>{calculations.roleHours[role]} ч</Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {calculations.roleCosts[role].toLocaleString('ru-RU')} ₽
                                    </Typography>
                                </TableCell>
                            ))}
                            <TableCell />
                            <TableCell align="center" sx={{ bgcolor: 'primary.100' }}>
                                <Typography variant="body1" fontWeight={700} color="primary.main">
                                    {calculations.totalHours} ч
                                </Typography>
                            </TableCell>
                        </TableRow>
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Statistics - Material 3 style */}
            <Collapse in={showStats}>
                <Box display="flex" gap={3} flexWrap="wrap" mt={2}>
                    {/* Pie chart - Material 3 surface */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            flex: 1,
                            minWidth: 320,
                            bgcolor: 'background.paper',
                            borderRadius: 6, // 24px Material 3
                            border: '1px solid',
                            borderColor: 'divider',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                        }}
                    >
                        <Typography variant="subtitle1" fontWeight={600} color="text.primary" mb={2}>
                            Распределение по ролям
                        </Typography>
                        <Box display="flex" alignItems="center" gap={2}>
                            {/* Donut chart */}
                            <Box sx={{ width: 160, height: 160, flexShrink: 0 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={pieData}
                                            dataKey="value"
                                            nameKey="name"
                                            cx="50%"
                                            cy="50%"
                                            innerRadius={55}
                                            outerRadius={75}
                                            paddingAngle={2}
                                        >
                                            {pieData.map((entry, idx) => (
                                                <Cell key={idx} fill={entry.color} />
                                            ))}
                                        </Pie>
                                        <RechartsTooltip
                                            formatter={(v, name) => [`${v} ч`, name]}
                                            contentStyle={{
                                                borderRadius: 12,
                                                border: 'none',
                                                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                                padding: '8px 12px',
                                            }}
                                        />
                                    </PieChart>
                                </ResponsiveContainer>
                            </Box>
                            {/* Legend */}
                            <Box sx={{ flex: 1 }}>
                                {pieData.map((item, idx) => (
                                    <Box
                                        key={item.name}
                                        display="flex"
                                        alignItems="center"
                                        justifyContent="space-between"
                                        sx={{
                                            py: 0.75,
                                            px: 1.5,
                                            mb: 0.5,
                                            borderRadius: 2,
                                            bgcolor: 'grey.50',
                                            '&:hover': { bgcolor: 'grey.100' },
                                        }}
                                    >
                                        <Box display="flex" alignItems="center" gap={1}>
                                            <Box
                                                sx={{
                                                    width: 10,
                                                    height: 10,
                                                    borderRadius: '50%',
                                                    bgcolor: item.color,
                                                }}
                                            />
                                            <Typography variant="body2" color="text.primary">
                                                {item.name}
                                            </Typography>
                                        </Box>
                                        <Box display="flex" alignItems="baseline" gap={0.5}>
                                            <Typography variant="body2" fontWeight={600}>
                                                {item.value}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                ч
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                                                {Math.round((item.value / calculations.totalHours) * 100)}%
                                            </Typography>
                                        </Box>
                                    </Box>
                                ))}
                            </Box>
                        </Box>
                    </Paper>

                    {/* Summary - Material 3 surface tint */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            flex: 1,
                            minWidth: 280,
                            background: 'linear-gradient(135deg, #FFF8F0 0%, #FFF0E0 100%)',
                            borderRadius: 6, // 24px Material 3
                            border: '1px solid',
                            borderColor: 'rgba(255, 152, 0, 0.2)',
                            boxShadow: '0 2px 8px rgba(255, 152, 0, 0.1)',
                        }}
                    >
                        <Typography variant="subtitle1" fontWeight={600} color="text.primary" mb={2}>
                            Итоговая смета
                        </Typography>

                        <Box
                            sx={{
                                display: 'flex',
                                flexDirection: 'column',
                                gap: 1.5,
                                p: 2,
                                bgcolor: 'rgba(255,255,255,0.7)',
                                borderRadius: 3,
                                mb: 2,
                            }}
                        >
                            <Box display="flex" justifyContent="space-between" alignItems="center">
                                <Typography variant="body2" color="text.secondary">
                                    Всего часов:
                                </Typography>
                                <Chip
                                    label={`${calculations.totalHours} ч`}
                                    size="small"
                                    sx={{
                                        fontWeight: 600,
                                        bgcolor: 'primary.50',
                                        color: 'primary.main',
                                    }}
                                />
                            </Box>

                            <Box display="flex" justifyContent="space-between" alignItems="center">
                                <Typography variant="body2" color="text.secondary">
                                    Базовая стоимость:
                                </Typography>
                                <Typography variant="body2" fontWeight={500}>
                                    {calculations.totalCost.toLocaleString('ru-RU')} ₽
                                </Typography>
                            </Box>

                            {calculations.totalWithRisk !== calculations.totalCost && (
                                <Box display="flex" justifyContent="space-between" alignItems="center">
                                    <Typography variant="body2" color="text.secondary">
                                        С учетом рисков:
                                    </Typography>
                                    <Typography variant="body2" fontWeight={500} color="warning.dark">
                                        {calculations.totalWithRisk.toLocaleString('ru-RU')} ₽
                                    </Typography>
                                </Box>
                            )}
                        </Box>

                        <Divider sx={{ borderStyle: 'dashed', borderColor: 'rgba(0,0,0,0.1)' }} />

                        {/* Typography-based ИТОГО - Material 3 style */}
                        <Box mt={2} textAlign="center">
                            <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.1em',
                                    fontSize: '0.7rem',
                                    display: 'block',
                                    mb: 0.5,
                                }}
                            >
                                Итого
                            </Typography>
                            <Typography
                                variant="h4"
                                fontWeight={700}
                                sx={{
                                    color: '#FF6B00',
                                    letterSpacing: '-0.02em',
                                    lineHeight: 1.2,
                                }}
                            >
                                {calculations.totalWithRisk.toLocaleString('ru-RU')} ₽
                            </Typography>
                        </Box>
                    </Paper>
                </Box>
            </Collapse>

            {/* Dialogs */}
            <Dialog open={openRoleDialog} onClose={() => setOpenRoleDialog(false)} maxWidth="xs" fullWidth>
                <DialogTitle fontWeight={600}>Добавить роль</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="Название роли"
                        fullWidth
                        value={newRoleName}
                        onChange={(e) => setNewRoleName(e.target.value)}
                        sx={{ mb: 2 }}
                    />
                    <TextField
                        margin="dense"
                        label="Ставка (₽/час)"
                        type="number"
                        fullWidth
                        value={newRoleRate}
                        onChange={(e) => setNewRoleRate(e.target.value)}
                    />
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 3 }}>
                    <Button onClick={() => setOpenRoleDialog(false)}>Отмена</Button>
                    <Button onClick={handleAddRole} variant="contained">Добавить</Button>
                </DialogActions>
            </Dialog>

            <Dialog open={openStageDialog} onClose={() => setOpenStageDialog(false)} maxWidth="xs" fullWidth>
                <DialogTitle fontWeight={600}>Добавить этап</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="Название этапа"
                        fullWidth
                        value={newStageName}
                        onChange={(e) => setNewStageName(e.target.value)}
                    />
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 3 }}>
                    <Button onClick={() => setOpenStageDialog(false)}>Отмена</Button>
                    <Button onClick={handleAddStage} variant="contained">Добавить</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}
