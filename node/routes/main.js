const express = require('express');
const path = require('path');
const dotenv = require('dotenv');

dotenv.config();  // 환경 변수 로드

const router = express.Router();

const PORT1 = process.env.PORT1 || 8000;
const PORT2 = process.env.PORT2 || 8500;
const FASTAPI_URL1 = process.env.FASTAPI_URL1;
const FASTAPI_URL2 = process.env.FASTAPI_URL2;
const NODE_URL1 = process.env.NODE_URL1;
const NODE_URL2 = process.env.NODE_URL2;

router.use(express.json());
router.use(express.urlencoded({ extended: true }));

router.get('/result', (req, res) => {
    res.render('result', {
        title: 'Express',
        PORT1,
        PORT2,
        FASTAPI_URL1,
        FASTAPI_URL2,
        NODE_URL1,
        NODE_URL2
    });
});

module.exports = router;

