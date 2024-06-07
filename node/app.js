const express = require('express');
const morgan = require('morgan');
const path = require('path');
const bodyParser = require('body-parser');
const cookieParser = require('cookie-parser');
const dotenv = require('dotenv');
const cors = require('cors');

dotenv.config();  // 환경 변수 로드

const app = express();

const PORT1 = process.env.PORT1 || 8000;
const PORT2 = process.env.PORT2 || 8500;
const FASTAPI_URL1 = process.env.FASTAPI_URL1;
const FASTAPI_URL2 = process.env.FASTAPI_URL2;
const NODE_URL1 = process.env.NODE_URL1;
const NODE_URL2 = process.env.NODE_URL2;

app.set('port', PORT1);
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

app.use(morgan('dev'));
app.use(cookieParser());
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

app.use(cors());

// 메인 라우터 가져오기
const mainRouter = require('./routes/main.js');
app.use('/', mainRouter);

app.listen(app.get('port'), () => {
    console.log(`Port1: Server Started on port ${PORT1}`);
});
