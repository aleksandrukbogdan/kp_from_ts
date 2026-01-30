import React, { useState, useMemo, useCallback } from 'react';
import {
    Box, Paper, Typography, TextField, IconButton, Tooltip, Chip,
    Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
    Button, Dialog, DialogTitle, DialogContent, DialogActions,
    Switch, FormControlLabel, Slider, Collapse, Alert, Divider
} from '@mui/material';
import {
    Add, Delete, Warning, TrendingUp, CompareArrows,
    ExpandMore, ExpandLess, Timeline
} from '@mui/icons-material';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, Legend } from 'recharts';

// Цвета для ролей
const ROLE_COLORS = [
    '#6750A4', '#0061A4', '#006E1C', '#BA1A1A', '#5D5F5F',
    '#7C5800', '#006874', '#8B5CF6', '#EC4899', '#10B981'
];

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
        return stages.map((stage, idx) => ({
            name: stage,
            hours: calculations.stageHours[stage] || 0,
            risk: riskCoefficients[stage] || 1,
            fill: ROLE_COLORS[idx % ROLE_COLORS.length]
        }));
    }, [stages, calculations.stageHours, riskCoefficients]);

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
                    <FormControlLabel
                        control={<Switch size="small" checked={showComparison} onChange={(e) => setShowComparison(e.target.checked)} />}
                        label={<Typography variant="caption">Сравнить с AI</Typography>}
                    />
                    <FormControlLabel
                        control={<Switch size="small" checked={showGantt} onChange={(e) => setShowGantt(e.target.checked)} />}
                        label={<Typography variant="caption">Gantt</Typography>}
                    />
                    <Button startIcon={<Add />} onClick={() => setOpenStageDialog(true)} size="small">Этап</Button>
                    <Button startIcon={<Add />} onClick={() => setOpenRoleDialog(true)} size="small">Роль</Button>
                </Box>
            </Box>

            {/* Gantt view - Material 3 style */}
            <Collapse in={showGantt}>
                <Paper
                    elevation={0}
                    sx={{
                        p: 3,
                        mb: 3,
                        bgcolor: 'background.paper',
                        borderRadius: 4,
                        border: '1px solid',
                        borderColor: 'divider',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                    }}
                >
                    <Box display="flex" alignItems="center" gap={1} mb={3}>
                        <Timeline sx={{ color: 'primary.main' }} />
                        <Typography variant="subtitle1" fontWeight={600}>
                            Визуализация этапов
                        </Typography>
                    </Box>
                    <ResponsiveContainer width="100%" height={Math.max(200, stages.length * 45)}>
                        <BarChart data={ganttData} layout="vertical" margin={{ left: 10, right: 30, top: 10, bottom: 10 }}>
                            <XAxis
                                type="number"
                                unit=" ч"
                                tick={{ fontSize: 12, fill: '#666' }}
                                axisLine={{ stroke: '#E0E0E0' }}
                                tickLine={{ stroke: '#E0E0E0' }}
                            />
                            <YAxis
                                type="category"
                                dataKey="name"
                                width={120}
                                tick={{ fontSize: 13, fill: '#333' }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <RechartsTooltip
                                formatter={(value) => [`${value} ч`, 'Часы']}
                                labelFormatter={(label) => `${label}`}
                                contentStyle={{
                                    borderRadius: 12,
                                    border: 'none',
                                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                    padding: '10px 14px',
                                }}
                            />
                            <Bar dataKey="hours" radius={[0, 8, 8, 0]} barSize={28}>
                                {ganttData.map((entry, idx) => (
                                    <Cell
                                        key={idx}
                                        fill={entry.fill}
                                        fillOpacity={entry.risk > 1 ? 0.85 : 1}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
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
                            borderRadius: 4,
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
                                            innerRadius={45}
                                            outerRadius={70}
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
                                            <Chip
                                                label={`${Math.round((item.value / calculations.totalHours) * 100)}%`}
                                                size="small"
                                                sx={{
                                                    ml: 1,
                                                    height: 20,
                                                    fontSize: '0.65rem',
                                                    bgcolor: `${item.color}20`,
                                                    color: item.color,
                                                    fontWeight: 600,
                                                }}
                                            />
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
                            borderRadius: 4,
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

                        <Box
                            display="flex"
                            justifyContent="space-between"
                            alignItems="center"
                            mt={2}
                            sx={{
                                p: 2,
                                bgcolor: 'primary.main',
                                borderRadius: 3,
                                color: 'white',
                            }}
                        >
                            <Typography variant="subtitle1" fontWeight={600}>
                                ИТОГО:
                            </Typography>
                            <Typography variant="h5" fontWeight={700}>
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
