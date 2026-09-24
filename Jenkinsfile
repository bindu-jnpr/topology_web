pipeline {
    agent any

    environment {
        IMAGE_NAME = "topology-web"
        IMAGE_TAG  = "${BUILD_NUMBER}"
        CONTAINER  = "topology-web"
    }

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {

        stage('Checkout') {
            steps {
                echo "Checking out code..."
                checkout scm
            }
        }

        stage('Lint') {
            steps {
                echo "Checking Python syntax..."
                sh '''
                    python3 -m py_compile main.py generator.py schemas.py
                    echo "Syntax OK"
                '''
            }
        }

        stage('Build') {
            steps {
                echo "Building Docker image..."
                sh "docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -t ${IMAGE_NAME}:latest ."
            }
        }

        stage('Smoke Test') {
            steps {
                echo "Running smoke test..."
                sh '''
                    docker run -d \
                        --name topology-web-test-${BUILD_NUMBER} \
                        -p 18000:8000 \
                        -e AWS_REGION=us-west-2 \
                        -e AWS_ACCESS_KEY_ID=dummy \
                        -e AWS_SECRET_ACCESS_KEY=dummy \
                        -e BEDROCK_MODEL_ID=dummy \
                        topology-web:${BUILD_NUMBER} \
                        uvicorn main:app --host 0.0.0.0 --port 8000

                    sleep 8

                    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/health)
                    echo "Health check: $STATUS"

                    docker stop topology-web-test-${BUILD_NUMBER} || true
                    docker rm   topology-web-test-${BUILD_NUMBER} || true

                    if [ "$STATUS" != "200" ]; then
                        echo "Smoke test failed"
                        exit 1
                    fi
                    echo "Smoke test passed"
                '''
            }
        }

        stage('Deploy') {
            when { branch 'main' }
            steps {
                echo "Deploying on this server..."
                withCredentials([file(credentialsId: 'TOPOLOGY_WEB_ENV', variable: 'ENV_FILE')]) {
                    sh """
                        # Stop old container
                        docker stop ${CONTAINER} 2>/dev/null || true
                        docker rm   ${CONTAINER} 2>/dev/null || true

                        # Start new container with real credentials and database mount
                        docker run -d \
                            --name ${CONTAINER} \
                            --restart always \
                            -p 8000:8000 \
                            --env-file \$ENV_FILE \
                            -v topology-web-data:/data \
                            ${IMAGE_NAME}:${IMAGE_TAG}

                        sleep 8

                        STATUS=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
                        echo "Health: \$STATUS"

                        if [ "\$STATUS" != "200" ]; then
                            echo "Deploy failed"
                            exit 1
                        fi
                        echo "Bot is live at http://localhost:8000"
                    """
                }
            }
        }

        stage('Cleanup') {
            steps {
                sh """
                    docker images ${IMAGE_NAME} --format '{{.Tag}}' \
                        | grep -v latest \
                        | sort -n \
                        | head -n -3 \
                        | xargs -r -I{} docker rmi ${IMAGE_NAME}:{} || true
                """
            }
        }
    }

    post {
        always {
            sh "docker rm -f topology-web-test-${BUILD_NUMBER} 2>/dev/null || true"
        }
    }
}
