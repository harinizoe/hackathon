from flask import Flask, render_template, request, jsonify, send_file, redirect
import os
from werkzeug.utils import secure_filename
from PIL import Image
from flask_pymongo import PyMongo
from gridfs import GridFS
from bson import ObjectId  # Import ObjectId to work with MongoDB IDs

app = Flask(__name__)

# Configurations
UPLOAD_FOLDER = 'uploads/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config["MONGO_URI"] = "mongodb://localhost:27017/urban_maintenance"
mongo = PyMongo(app)
fs = GridFS(mongo.db)

# Ensure the uploads folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Allowed file extensions for images
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Check if the file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Compress image before saving to GridFS
def compress_image(image_path, quality=85):
    img = Image.open(image_path)
    img.save(image_path, optimize=True, quality=quality)

# Front page route
@app.route('/')
def frontpage():
    return render_template('front.html')

# Report page route
@app.route('/report')
def report():
    return render_template('index.html')

# Handle issue report submission
@app.route('/report-issue', methods=['POST'])
def report_issue():
    try:
        data = request.form
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        category = data.get('issue_category', '').strip()
        address = data.get('address', '').strip()
        description = data.get('description', '').strip()
        file = request.files.get('geotagImage')

        # Validate all fields are filled
        if not all([name, email, category, address, description]):
            return jsonify({"status": "error", "message": "All fields are required."}), 400

        geotagImage_id = None  # Will store the image ID if an image is uploaded

        # If there's a file and it's an allowed image type
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)  # Save to disk temporarily
            compress_image(file_path)  # Compress the image

            # Save the compressed image to GridFS
            with open(file_path, 'rb') as image_file:
                geotagImage_id = fs.put(image_file, filename=filename)

        # Prepare the issue data for MongoDB
        issue_data = {
            'name': name,
            'email': email,
            'issue_category': category,
            'address': address,
            'description': description,
            'geotagImage_id': geotagImage_id,
            'status': 'reported'  # Default status
        }

        # Insert the issue report into the database
        mongo.db.issues.insert_one(issue_data)

        return jsonify({"status": "success", "message": "Issue reported successfully!"})

    except Exception as e:
        print(f"Error occurred: {e}")  # Log the error for debugging
        return jsonify({"status": "error", "message": "There was an error submitting the form."}), 500

# Admin dashboard route
@app.route('/admin')
def admin():
    issues = mongo.db.issues.find({"status": {"$ne": "resolved"}})
    categorized_issues = {}
    for issue in issues:
        category = issue.get('issue_category', 'Others')  # Default to 'Others' if category is missing
        if category not in categorized_issues:
            categorized_issues[category] = []
        categorized_issues[category].append(issue)

    return render_template('admin.html', categorized_issues=categorized_issues)

# Update the status of an issue
@app.route('/update-status/<issue_id>', methods=['POST'])
def update_status(issue_id):
    new_status = request.form.get('status')
    mongo.db.issues.update_one({'_id': ObjectId(issue_id)}, {'$set': {'status': new_status}})
    return redirect('/admin')

# Fetch and serve the image from GridFS
@app.route('/get-image/<image_id>')
def get_image(image_id):
    try:
        # Fetch the image from GridFS using ObjectId
        image = fs.get(ObjectId(image_id))
        return send_file(image, mimetype='image/jpeg')
    except Exception as e:
        print(f"Error retrieving image: {e}")  # Log the error for debugging
        return jsonify({"status": "error", "message": "Image not found."}), 404

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
